function plot_flow(studyDir)
% Run study.py first. Its slice is [y,x]; the sampled volume is [z,y,x].
p = load(fullfile(studyDir,'plot-data.mat'));
g = structfun(@double,p.dims,'UniformOutput',false);
p.grid = double(p.grid); D = g.body_diameter; d = double(p.d);
x = ((0:p.grid(1)-1)+0.5)/d*D-p.upstream*D;
y = ((0:p.grid(2)-1)+0.5-p.grid(2)/2)/d*D;
z = ((0:p.grid(3)-1)+0.5-p.grid(3)/2)/d*D;
sub = p.stride;
xs = x(1:sub:end); ys = y(1:sub:end); zs = z(1:sub:end);
keep = xs >= -15 & xs < g.overall+5*D;
volume = permute(p.volume,[2 3 1]); interior = permute(p.interior,[2 3 1]);
volume(interior~=0) = NaN;
[X,Y,Z] = meshgrid(xs(keep),ys,zs);
fig = figure('Visible','off','Color','white','Position',[100 100 1030 700]);
clean = onCleanup(@() close(fig));
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');
tiledlayout(fig,2,2,'TileSpacing','compact','Padding','compact');
ax = nexttile([1 2]); hold(ax,'on');
surface = isosurface(X,Y,Z,volume(:,keep,:),0.80);
patch(ax,surface,'FaceColor',[0.10 .55 .68],'EdgeColor','none','FaceAlpha',.32);
% Show the physical outer profile and four zero-thickness planforms.
theta = linspace(0,2*pi,129);
r = [0 D/2 D/2]'; stations = [0 g.nose_length g.overall]';
surf(ax,stations*ones(size(theta)),r*cos(theta),r*sin(theta), ...
    'EdgeColor','none','FaceColor',[.32 .37 .41]);
root = g.overall-g.fin_tail_inset-g.fin_root;
xf = root+[0 g.fin_sweep g.fin_sweep+g.fin_tip g.fin_root];
rad = D/2+[0 g.fin_span g.fin_span 0];
for blade=0:3
    patch(ax,xf,rad*cos(blade*pi/2),rad*sin(blade*pi/2),[.86 .49 .16], ...
        'EdgeColor',[.55 .31 .15]);
end
axis(ax,'equal'); view(ax,[16 16]); xlim(ax,[-20 g.overall+5*D]);
ylim(ax,[-200 200]); zlim(ax,[-200 200]); grid(ax,'on');
xlabel(ax,'先端からの距離 (mm)'); ylabel(ax,'横 (mm)'); zlabel(ax,'高さ (mm)');
camlight(ax,'headlight'); lighting(ax,'gouraud');
title(ax,'正面風 15 m/s　青は流れ方向速度が主流の80%になる瞬間の面');
ax=nexttile;
im=imagesc(ax,x,y,p.ux,[-.25 1.25]); im.AlphaData=~logical(p.solid);
set(ax,'YDir','normal','Color',[.28 .31 .35]); axis(ax,'image'); hold(ax,'on');
xlim(ax,[-30 g.overall+4*D]); ylim(ax,[-190 190]); colormap(ax,parula);
cb=colorbar(ax); cb.Label.String='流れ方向速度 / 主流速度';
xlabel(ax,'先端からの距離 (mm)'); ylabel(ax,'横 (mm)'); title(ax,'機体中心付近の速度断面');
ax=nexttile; plot(ax,[10 16 24 32 40],p.grids,'-o','LineWidth',2, ...
    'Color',[.12 .44 .53],'MarkerFaceColor',[.12 .44 .53]);
hold(ax,'on'); yline(ax,p.prior,'--','前回の飛行計算','Color',[.65 .28 .12]);
grid(ax,'on'); ylim(ax,[0 max(p.grids)*1.13]); xticks(ax,[10 16 24 32 40]);
xlabel(ax,'胴径あたりの格子数'); ylabel(ax,'平均抗力係数'); title(ax,'正面風での格子依存性');
exportgraphics(fig,fullfile(studyDir,'bottle-flow.png'),'Resolution',145);
end
