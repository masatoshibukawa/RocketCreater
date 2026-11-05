function r=collar_fem(input,cfg,payload,thermal,outDir)
% Idealised solid printed annulus. Outer cylindrical face is fully clamped.
% Uniform top load, no contact, infill, layer anisotropy or attachment compliance.
p=cfg.collar; g=input.assembly.print_parts;
ri=g.collar_inner_mm/2000; ro=g.collar_outer_mm/2000; h=g.thickness_mm/1000;
F=payload.collar_axial_load_scenario_n; traction=F/(pi*(ro^2-ri^2));
r.provisional=true;r.scope='3D linear elastic annulus, uniform axial top load and rigid outer clamp.';
r.load_n=F;r.temperature_C=thermal.hot_mount_C;r.reference_C=p.reference_C;
rows={};
for k=1:numel(p.hmax_m)
    model=femodel(AnalysisType="structuralStatic",Geometry=multicylinder([ri ro],h,Void=[true false]));
    outer=nearestFace(model.Geometry,[ro,0,h/2]); top=nearestFace(model.Geometry,[(ri+ro)/2,0,h]);
    assert(outer~=top);
    model.MaterialProperties=materialProperties(YoungsModulus=p.E_pa,PoissonsRatio=p.nu, ...
        MassDensity=p.rho_kg_m3,CTE=p.CTE_per_K);
    model.FaceBC(outer)=faceBC(Constraint="fixed");
    model=generateMesh(model,Hmax=p.hmax_m(k),Hmin=p.hmax_m(k)/3,GeometricOrder="quadratic");
    model.FaceLoad(top)=faceLoad(SurfaceTraction=[0;0;-traction]);
    model.ReferenceTemperature=p.reference_C;
    model.CellLoad=cellLoad(Temperature=p.reference_C);
    mech=solve(model);
    reaction=evaluateReaction(mech,Face=outer);
    recoveredError=abs(reaction.Fz-F)/F;
    % Stress recovery near an ideal clamp is not a conservative nodal reaction.
    % Check equilibrium with the original FE operator before eliminating constraints.
    matrices=assembleFEMatrices(model,'KAFQG');
    u=[mech.Displacement.ux;mech.Displacement.uy;mech.Displacement.uz];
    residual=(matrices.K+matrices.A+matrices.Q)*u-matrices.F-matrices.G;
    mesh=model.Geometry.Mesh;nn=size(mesh.Nodes,2);
    fixed=findNodes(mesh,'region','Face',outer);
    reactionFE=sum(residual(2*nn+fixed));
    appliedFE=-sum(matrices.F(2*nn+1:end)+matrices.G(2*nn+1:end));
    balance=abs(reactionFE-appliedFE)/appliedFE;
    loadIntegrationError=abs(appliedFE-F)/F;
    free=setdiff(1:3*nn,[fixed,fixed+nn,fixed+2*nn]);
    assert(norm(residual(free),Inf)/F<1e-7,'Unbalanced free-node FE equations.');
    fprintf('Collar %.2f mm: nodal balance %.4g; recovered traction error %.4g\n',p.hmax_m(k)*1000,balance,recoveredError);
    clear matrices residual
    model.FaceLoad(top)=faceLoad(SurfaceTraction=[0;0;0]);
    model.CellLoad=cellLoad(Temperature=thermal.hot_mount_C);
    heat=solve(model);
    model.FaceLoad(top)=faceLoad(SurfaceTraction=[0;0;-traction]);
    both=solve(model);
    combined=[both.Displacement.ux,both.Displacement.uy,both.Displacement.uz];
    sumdisp=[mech.Displacement.ux+heat.Displacement.ux,mech.Displacement.uy+heat.Displacement.uy, ...
        mech.Displacement.uz+heat.Displacement.uz];
    err=norm(combined-sumdisp,'fro')/norm(combined,'fro');assert(err<1e-6,'Linear superposition failed.');
    % Exclude the ideal clamp edge; point stress there is not a converged allowable.
    nodes=model.Geometry.Mesh.Nodes; rad=hypot(nodes(1,:),nodes(2,:));
    away=rad<ro-0.002 & rad>ri+0.001;
    rows{k}=struct('hmax_m',p.hmax_m(k),'nodes',size(nodes,2), ...
        'max_displacement_mm',max(both.Displacement.Magnitude)*1000, ...
        'mechanical_vm_away_MPa',max(mech.VonMisesStress(away))/1e6, ...
        'thermal_vm_away_MPa',max(heat.VonMisesStress(away))/1e6, ...
        'combined_vm_away_MPa',max(both.VonMisesStress(away))/1e6, ...
        'combined_vm_point_max_MPa',max(both.VonMisesStress)/1e6, ...
        'superposition_relative',err,'force_balance_relative',balance, ...
        'recovered_traction_error_relative',recoveredError, ...
        'load_integration_error_relative',loadIntegrationError); %#ok<AGROW>
end
rows=[rows{:}];r.mesh=rows;
r.refinement_displacement_relative=abs(rows(end).max_displacement_mm-rows(end-1).max_displacement_mm)/rows(end).max_displacement_mm;
r.refinement_interior_stress_relative=abs(rows(end).combined_vm_away_MPa-rows(end-1).combined_vm_away_MPa)/rows(end).combined_vm_away_MPa;
r.displacement_grid_check=r.refinement_displacement_relative<0.05;
r.interior_stress_grid_check=r.refinement_interior_stress_relative<0.1;
r.force_balance_check=rows(end).force_balance_relative<1e-4;
r.load_integration_check=rows(end).load_integration_error_relative<0.005;
r.recovered_boundary_traction_converged=false;
r.safety_status='unknown: solid isotropic material, distributed load and rigid clamp are unvalidated';
fig=figure('Visible','off','Color','white','Position',[20 20 1100 530]);clean=onCleanup(@()close(fig)); %#ok<NASGU>
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');
tiledlayout(1,2,'TileSpacing','loose','Padding','loose');
nexttile;pdeplot3D(model.Geometry.Mesh,ColorMapData=both.VonMisesStress/1e6);view(25,25);
title('機械＋拘束熱応力 (MPa)','FontSize',12);xlabel('x (m)');ylabel('y (m)');zlabel('z (m)');
nexttile;pdeplot3D(model.Geometry.Mesh,ColorMapData=both.Displacement.Magnitude*1000, ...
    Deformation=both.Displacement,DeformationScaleFactor=100);view(25,25);
title('変位量 (mm)・変形は 100 倍表示','FontSize',12);xlabel('x (m)');ylabel('y (m)');zlabel('z (m)');
annotation(fig,'textbox',[.04 .015 .92 .06],'String', ...
    sprintf('保持リング｜仮の荷重 %.1f N・温度 %.1f°C・外周を完全固定・中実等方性',F,thermal.hot_mount_C), ...
    'EdgeColor','none','HorizontalAlignment','center','FontName','Meiryo','FontSize',11);
exportgraphics(fig,fullfile(outDir,'collar-fem.png'),'Resolution',160);
save(fullfile(outDir,'collar-fields.mat'),'model','mech','heat','both');
end
