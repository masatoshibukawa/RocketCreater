// Stationary linear interpolated bounce-back (Bouzidi et al., 2001).
// Geometry lengths are in body diameters. Fin faces have their specified thickness.
// This optional path supports a sphere or a cone/cylinder body with four fins.
__device__ bool clip_plane(float value,float slope,float &lo,float &hi) {
    // Retain value + t*slope >= 0.
    if(fabsf(slope)<1e-12f) return value>=0;
    float t=-value/slope;
    if(slope>0) lo=fmaxf(lo,t); else hi=fminf(hi,t);
    return lo<=hi;
}
__device__ float fin_distance(float x,float y,float z,float vx,float vy,float vz,const float *g) {
    float best=2.f,root=g[0]-g[6]-g[2];
    for(int blade=0;blade<4;++blade) {
        float r=(blade==0 ? y : blade==1 ? z : blade==2 ? -y : -z)-.5f-g[14];
        float t=(blade==0 ? z : blade==1 ? -y : blade==2 ? -z : y);
        float dr=(blade==0 ? vy : blade==1 ? vz : blade==2 ? -vy : -vz);
        float dt=(blade==0 ? vz : blade==1 ? -vy : blade==2 ? -vz : vy);
        float lo=0,hi=1,sweep=g[5]/g[4],taper=(g[3]-g[2])/g[4];
        float side=t-g[9]*(x-root-.5f*g[2]), change=dt-g[9]*vx;
        if(clip_plane(r,dr,lo,hi) && clip_plane(g[4]-r,-dr,lo,hi)
            && clip_plane(x-root-sweep*r,vx-sweep*dr,lo,hi)
            && clip_plane(g[2]+(sweep+taper)*r-(x-root),(sweep+taper)*dr-vx,lo,hi)
            && clip_plane(.5f*g[13]-side,-change,lo,hi)
            && clip_plane(.5f*g[13]+side,change,lo,hi)) best=fminf(best,lo);
        // External mounting shoe envelope; holes/fillets and strap roughness unresolved.
        // The fin root sits at its outer radius, not inside the pressure bottle.
        if(g[14]>0 && g[15]>0) {
            lo=0; hi=1;
            if(clip_plane(r+g[14],dr,lo,hi) && clip_plane(-r,-dr,lo,hi)
                && clip_plane(x-root,vx,lo,hi) && clip_plane(g[2]-x+root,-vx,lo,hi)
                && clip_plane(.5f*g[15]-t,-dt,lo,hi)
                && clip_plane(.5f*g[15]+t,dt,lo,hi)) best=fminf(best,lo);
        }
    }
    return best;
}
__device__ void root_hit(float t,float x,float y,float z,float vx,float vy,float vz,
        float xmin,float xmax,float &best) {
    if(t>=0 && t<=1 && x+t*vx>=xmin-1e-6f && x+t*vx<=xmax+1e-6f)
        best=fminf(best,t);
}
__device__ void quadratic_hits(float a,float b,float c,float x,float y,float z,
        float vx,float vy,float vz,float xmin,float xmax,float &best) {
    if(fabsf(a)<1e-12f) {
        if(fabsf(b)>1e-12f) root_hit(-c/b,x,y,z,vx,vy,vz,xmin,xmax,best);
    } else {
        float disc=b*b-4*a*c;
        if(disc>=0) {
            float s=sqrtf(disc);
            root_hit((-b-s)/(2*a),x,y,z,vx,vy,vz,xmin,xmax,best);
            root_hit((-b+s)/(2*a),x,y,z,vx,vy,vz,xmin,xmax,best);
        }
    }
}
__device__ float exact_distance(int shape,float x,float y,float z,
        float vx,float vy,float vz,const float *g) {
    float best=2.f;
    if(shape==0) return best;
    if(shape==1) {
        quadratic_hits(vx*vx+vy*vy+vz*vz,2*((x-.5f)*vx+y*vy+z*vz),
            (x-.5f)*(x-.5f)+y*y+z*z-.25f,x,y,z,vx,vy,vz,-1e6f,1e6f,best);
        return best;
    }
    float c=.25f/(g[1]*g[1]);
    quadratic_hits(vy*vy+vz*vz-c*vx*vx,2*(y*vy+z*vz-c*x*vx),
        y*y+z*z-c*x*x,x,y,z,vx,vy,vz,0,g[1],best);
    quadratic_hits(vy*vy+vz*vz,2*(y*vy+z*vz),y*y+z*z-.25f,
        x,y,z,vx,vy,vz,g[1],g[0],best);
    if(fabsf(vx)>1e-12f) {
        float t=(g[0]-x)/vx;
        if(t>=0 && t<=1 && (y+t*vy)*(y+t*vy)+(z+t*vz)*(z+t*vz)<=.25f)
            best=fminf(best,t);
    }
    return fminf(best,fin_distance(x,y,z,vx,vy,vz,g));
}
extern "C" __global__ void wall_setup(const unsigned *mask,const int *ids,int count,
        int *lookup,float *fractions,int nx,int ny,int nz,int d,int shape,const float *g) {
    int j=blockIdx.x*blockDim.x+threadIdx.x;
    if(j>=count) return;
    int k=ids[j]; lookup[k]=j;
    float dx=1.f/d,x=(k%nx+.5f)*dx-g[10],y=(k/nx%ny+.5f-ny*.5f)*dx;
    float z=(k/(nx*ny)+.5f-nz*.5f)*dx;
    float xb=g[11]*(x-g[8])-g[12]*y+g[8],yb=g[12]*(x-g[8])+g[11]*y;
    for(int i=1;i<19;++i) if(mask[k] & (1u<<i)) {
        float vx=-ex[i]*dx,vy=-ey[i]*dx,vz=-ez[i]*dx;
        fractions[j*19+i]=fmaxf(1e-5f,exact_distance(shape,xb,yb,z,
            g[11]*vx-g[12]*vy,g[12]*vx+g[11]*vy,vz,g));
    }
}
__device__ float reflected(const float *src,const unsigned *mask,const int *lookup,
        const float *fractions,int k,int i,int n,int nx,int ny,int mode) {
    int opposite=(i%2) ? i+1 : i-1;
    float out=src[opposite*n+k];
    if(!mode) return out;
    float q=fractions[lookup[k]*19+i];
    if(q>=.5f) return (out+(2*q-1)*src[i*n+k])/(2*q);
    // Do not interpolate through another wall in thin fluid gaps.
    if(mask[k] & (1u<<opposite)) return out;
    int j=k+ex[i]+ey[i]*nx+ez[i]*nx*ny;
    return 2*q*out+(1-2*q)*src[opposite*n+j];
}
