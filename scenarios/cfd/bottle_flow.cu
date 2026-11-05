// D3Q19, regularized second-order nonequilibrium and local Smagorinsky viscosity.
// f stores departures from the rest weights. Length and time in lattice units.
__constant__ int ex[19]={0,1,-1,0,0,0,0,1,-1,1,-1,1,-1,1,-1,0,0,0,0};
__constant__ int ey[19]={0,0,0,1,-1,0,0,1,-1,-1,1,0,0,0,0,1,-1,1,-1};
__constant__ int ez[19]={0,0,0,0,0,1,-1,0,0,0,0,1,-1,-1,1,1,-1,-1,1};
__device__ float weight(int i) {return i==0 ? 1.f/3 : i<=6 ? 1.f/18 : 1.f/36;}
__device__ float eq(int i,float dr,float u,float v,float w) {
    float eu=ex[i]*u+ey[i]*v+ez[i]*w;
    return weight(i)*(dr+(1+dr)*(3*eu+4.5f*eu*eu-1.5f*(u*u+v*v+w*w)));
}

// Coordinates in body diameters; origin at nose. 0 empty, 1 sphere, 2 flat
// base, 3 recessed skirt. g = length, nose, root, tip, span, sweep, fin inset,
// skirt length, CG, tan(cant). Recess geometry is an unmeasured sensitivity case.
__device__ bool solid(int shape,float x,float y,float z,float dx,const float *g) {
    float r2=y*y+z*z;
    if(shape==0) return false;
    if(shape==1) return (x-.5f)*(x-.5f)+r2 < .25f;
    if(x<0 || x>g[0] || r2>=.25f) return false;
    if(x<g[1]) {
        float s=x/g[1];
        return r2 < .25f*(shape==4 ? s*(2.f-s) : s*s);
    }
    if(shape==2 || shape==4 || x<g[0]-g[7]) return true;
    float s=(g[0]-x)/g[7];
    float radius=.15f+.35f*s;
    return r2 < radius*radius || r2 > (.5f-dx)*(.5f-dx);
}

__device__ bool fin_link(float x,float y,float z,float vx,float vy,float vz,const float *g) {
    float root=g[0]-g[6]-g[2];
    if(x<root-0.2f || x>g[0]+0.2f) return false;
    for(int blade=0;blade<4;++blade) {
        float r=(blade==0 ? y : blade==1 ? z : blade==2 ? -y : -z);
        float t=(blade==0 ? z : blade==1 ? -y : blade==2 ? -z : y);
        float dr=(blade==0 ? vy : blade==1 ? vz : blade==2 ? -vy : -vz);
        float dt=(blade==0 ? vz : blade==1 ? -vy : blade==2 ? -vz : vy);
        float side=t-g[9]*(x-root-.5f*g[2]), change=dt-g[9]*vx;
        if((side>=0)==(side+change>=0)) continue;
        float fraction=-side/change;
        float span=(r+fraction*dr-.5f)/g[4];
        float chord=x+fraction*vx-root-g[5]*span;
        if(span>=0 && span<=1 && chord>=0 && chord<=g[2]+(g[3]-g[2])*span) return true;
    }
    return false;
}

extern "C" __global__ void setup(unsigned *mask,float *f,int nx,int ny,int nz,
        int d,int shape,const float *g,float u,float v) {
    int n=nx*ny*nz,k=blockIdx.x*blockDim.x+threadIdx.x;
    if(k>=n) return;
    float dx=1.f/d,x=(k%nx+.5f)*dx-g[10],y=(k/nx%ny+.5f-ny*.5f)*dx;
    float z=(k/(nx*ny)+.5f-nz*.5f)*dx;
    // Optional body rotation keeps the incoming flow aligned with the open x faces.
    // Transform domain coordinates into nose-based body coordinates about dry CG.
    float xb=g[11]*(x-g[8])-g[12]*y+g[8], yb=g[12]*(x-g[8])+g[11]*y;
    x=xb; y=yb;
    unsigned bits=0;
    if(solid(shape,x,y,z,dx,g)) bits=1u<<31;
    else for(int i=1;i<19;++i) {
        float vx=-ex[i]*dx,vy=-ey[i]*dx,vz=-ez[i]*dx;
        float bx=g[11]*vx-g[12]*vy, by=g[12]*vx+g[11]*vy;
        vx=bx; vy=by;
        if(solid(shape,x+vx,y+vy,z+vz,dx,g) ||
           (shape>=2 && fin_link(x,y,z,vx,vy,vz,g))) bits |= 1u<<i;
    }
    mask[k]=bits;
    for(int i=0;i<19;++i) f[i*n+k]=eq(i,0,u,v,0);
}

// Sample the SAME incoming populations used by advance, before collision.
// Pressure is at adjacent fluid-cell centres, not an extrapolated wall value.
// Force is momentum exchange (pressure + viscous), not pressure-only quadrature.
extern "C" __global__ void surface_probe(const float *src,const unsigned *mask,
        const int *ids,int count,int nx,int ny,int nz,float *stats) {
    int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j>=count) return;
    int k=ids[j], n=nx*ny*nz, y=k/nx%ny,z=k/(nx*ny);
    unsigned bits=mask[k];
    float dr=0,fx=0,fy=0,fz=0;
    for(int i=0;i<19;++i) {
        int a=ex[i],b=ey[i],c=ez[i]; float h;
        if(bits & (1u<<i)) {
            int opposite=(i%2) ? i+1 : i-1;
            h=src[opposite*n+k];
            fx-=2*a*h; fy-=2*b*h; fz-=2*c*h;
        } else {
            int index=k-a-b*nx-c*nx*ny;
            if(y-b<0) index+=ny*nx;
            if(y-b>=ny) index-=ny*nx;
            if(z-c<0) index+=n;
            if(z-c>=nz) index-=n;
            h=src[i*n+index];
        }
        dr+=h;
    }
    stats[j]+=dr; stats[count+j]+=fx; stats[2*count+j]+=fy; stats[3*count+j]+=fz;
}

extern "C" __global__ void advance(const float *src,float *dst,const unsigned *mask,
        int nx,int ny,int nz,int d,float inlet_u,float inlet_v,float tau,float cs,
        float cg_from_inlet,int sample,float *forces) {
    int k=blockIdx.x*blockDim.x+threadIdx.x,n=nx*ny*nz;
    if(k>=n || mask[k]>>31) return;
    int x=k%nx,y=k/nx%ny,z=k/(nx*ny);
    if(x==0 || x==nx-1) {
        for(int i=0;i<19;++i) dst[i*n+k]=x==0 ? eq(i,0,inlet_u,inlet_v,0) : src[i*n+k-1];
        return;
    }
    float dr=0,mx=0,my=0,mz=0,xx=0,yy=0,zz=0,xy=0,xz=0,yz=0;
    float fx=0,fy=0,fz=0;
    unsigned bits=mask[k];
    #pragma unroll
    for(int i=0;i<19;++i) {
        int a=ex[i],b=ey[i],c=ez[i]; float h;
        if(bits & (1u<<i)) {
            int opposite=(i%2) ? i+1 : i-1;
            h=src[opposite*n+k];
            if(sample) {fx-=2*a*h; fy-=2*b*h; fz-=2*c*h;}
        } else {
            int j=k-a-b*nx-c*nx*ny;
            if(y-b<0) j+=ny*nx;
            if(y-b>=ny) j-=ny*nx;
            if(z-c<0) j+=n;
            if(z-c>=nz) j-=n;
            h=src[i*n+j];
        }
        dr+=h; mx+=a*h; my+=b*h; mz+=c*h;
        xx+=a*a*h; yy+=b*b*h; zz+=c*c*h; xy+=a*b*h; xz+=a*c*h; yz+=b*c*h;
    }
    float rho=1+dr,u=mx/rho,v=my/rho,w=mz/rho;
    xx-=dr/3+mx*u; yy-=dr/3+my*v; zz-=dr/3+mz*w;
    xy-=mx*v; xz-=mx*w; yz-=my*w;
    float stress=sqrtf(xx*xx+yy*yy+zz*zz+2*(xy*xy+xz*xz+yz*yz));
    float effective=.5f*(tau+sqrtf(tau*tau+18.f*1.41421356f*cs*cs*stress/rho));
    float relax=1-1/effective;
    float ramp=fmaxf(0.f,(x-(nx-2*d))/(2.f*d));
    float sponge=.06f*ramp*ramp;
    #pragma unroll
    for(int i=0;i<19;++i) {
        int a=ex[i],b=ey[i],c=ez[i];
        float proj=a*a*xx+b*b*yy+c*c*zz-(xx+yy+zz)/3+2*(a*b*xy+a*c*xz+b*c*yz);
        float post=eq(i,dr,u,v,w)+relax*4.5f*weight(i)*proj;
        dst[i*n+k]=post+sponge*(eq(i,0,inlet_u,inlet_v,0)-post);
    }
    if(sample && bits) {
        float rx=(x+.5f)/d-cg_from_inlet,ry=(y+.5f-.5f*ny)/d,rz=(z+.5f-.5f*nz)/d;
        atomicAdd(forces,fx); atomicAdd(forces+1,fy); atomicAdd(forces+2,fz);
        // The half-link offset is parallel to its impulse and has zero moment.
        atomicAdd(forces+3,ry*fz-rz*fy); atomicAdd(forces+4,rz*fx-rx*fz);
        atomicAdd(forces+5,rx*fy-ry*fx);
    }
}

extern "C" __global__ void cut(const float *src,const unsigned *mask,float *slice,
                               int nx,int ny,int nz) {
    int j=blockIdx.x*blockDim.x+threadIdx.x,plane=nx*ny,n=plane*nz;
    if(j>=plane) return;
    int k=j+plane*(nz/2);
    float dr=0,mx=0,my=0;
    for(int i=0;i<19;++i) {float h=src[i*n+k]; dr+=h; mx+=ex[i]*h; my+=ey[i]*h;}
    slice[j]=mx/(1+dr); slice[j+plane]=my/(1+dr); slice[j+2*plane]=dr;
    slice[j+3*plane]=mask[k]>>31;
}

// Strided end-of-run sample for viewing a three-dimensional wake.
extern "C" __global__ void volume(const float *src,const unsigned *mask,float *out,
                                  int nx,int ny,int nz,int stride) {
    int sx=(nx+stride-1)/stride,sy=(ny+stride-1)/stride,sz=(nz+stride-1)/stride;
    int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j>=sx*sy*sz) return;
    int k=stride*((j%sx)+nx*((j/sx)%sy)+nx*ny*(j/(sx*sy))),n=nx*ny*nz;
    float dr=0,mx=0;
    for(int i=0;i<19;++i) {float h=src[i*n+k]; dr+=h; mx+=ex[i]*h;}
    out[j]=mx/(1+dr);
    out[j+sx*sy*sz]=mask[k]>>31;
}
