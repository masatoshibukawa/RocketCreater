function r=body_response(input,cfg,payload,thermal,outDir)
% Membrane demands on a cylindrical wall and separate unpressurised sleeve.
p=cfg.body; radius=input.assembly.dimensions_mm.body_diameter/2000;
pg=input.design.initial_gauge_pressure_pa;
t=p.wall_thicknesses_m;
hoop=pg*radius./t; axial=hoop/2; vm=sqrt(hoop.^2+axial.^2-hoop.*axial);
r.provisional=true;r.wall=struct('thickness_m',t,'hoop_MPa',hoop/1e6, ...
    'axial_MPa',axial/1e6,'von_mises_MPa',vm/1e6);
% Von Mises is reported as a scalar diagnostic, not a PET/print failure criterion.
r.pressure_allowable_status='unknown: thickness map, temperature, damage and maker limits absent';
ts=p.sleeve_thickness_m;A=2*pi*radius*ts;I=pi*radius^3*ts;
N=payload.whole_body_axial_load_scenario_n;M=N*p.payload_eccentricity_m;
r.sleeve=struct('axial_load_scenario_n',N,'eccentricity_m',p.payload_eccentricity_m, ...
    'axial_plus_bending_stress_MPa',(N/A+M*radius/I)/1e6, ...
    'average_overlap_shear_MPa',N/(2*pi*radius*p.joint_overlap_m)/1e6, ...
    'ideal_elastic_cylinder_buckling_MPa',p.E_pa/sqrt(3*(1-p.nu^2))*ts/radius/1e6, ...
    'buckling_status','not_qualified: perfect-shell formula excludes seams, ovality, cutouts and imperfections');
dT=thermal.sun(end).skin_C(end)-cfg.collar.reference_C;
r.thermal=struct('skin_delta_K',dT,'free_axial_strain',p.CTE_per_K*dT, ...
    'fully_restrained_uniaxial_stress_MPa',p.E_pa*p.CTE_per_K*dT/1e6, ...
    'load_case','separate unpressurised hot wait; no pressure plus thermal worst-case sum');
% Thin-wall reference checks from force equilibrium.
assert(max(abs(hoop.*t*2*radius-pg*2*radius^2))<1e-9);
assert(max(abs(axial.*t*2*pi*radius-pg*pi*radius^2))<1e-9);
fig=figure('Visible','off','Color','white','Position',[20 20 1000 430]);clean=onCleanup(@()close(fig)); %#ok<NASGU>
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');tiledlayout(1,2);
nexttile;plot(t*1000,[hoop,axial,vm]/1e6,'o-','LineWidth',2); grid on;
xlabel('仮の肉厚 (mm)');ylabel('膜応力 (MPa)');legend('周方向','軸方向','ミーゼス相当');
title(sprintf('胴体の直円筒近似・ゲージ圧 %.0f kPa',pg/1000));
nexttile;axis off
text(0,.9,{sprintf('非加圧スリーブへの荷重ケース %.1f N',N); ...
    sprintf('偏心込みの公称応力 %.2f MPa',r.sleeve.axial_plus_bending_stress_MPa); ...
    '直円筒の平均応力。肩・底・口部は対象外'; '接合部の局所剥離、座屈、クリープは未判定'; ...
    '材料許容値がないため安全率を出さない'},'FontSize',10,'VerticalAlignment','top');
exportgraphics(fig,fullfile(outDir,'body.png'),'Resolution',150);
end
