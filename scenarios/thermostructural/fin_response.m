function r = fin_response(input,cfg,thermal,outDir)
% Linear bending/torsion screening, followed by a gated local pitch model.
p=cfg.fin; g=input.assembly.dimensions_mm;
r.provisional=true; r.scope='Static strip torsion and spanwise bending, no flutter or 6DOF flight.';
names=["bonded","two_slipping_plies","warm_bonded","stiffer_root"];
factor=[1,0.25,thermal.assumed_warm_fin_stiffness_ratio,1]; rootFactor=[1,1,factor(3),10];
qvalues=[0.5*1.2*15^2,input.max_dynamic_pressure_pa];
cases=struct([]); ncase=0;
for j=1:numel(names)
    for q=qvalues
        for offset=p.aerodynamic_offset_chord_fractions'
            a=solveFin(input,p,q,offset,factor(j),rootFactor(j),80);
            fine=solveFin(input,p,q,offset,factor(j),rootFactor(j),160);
            ncase=ncase+1;
            a.case_name=names(j); a.refinement_relative=NaN;
            if a.static_equilibrium_exists && fine.static_equilibrium_exists
                a.refinement_relative=abs(a.tip_deflection_m-fine.tip_deflection_m)/max(abs(fine.tip_deflection_m),1e-12);
                assert(a.refinement_relative<0.005,'Fin mesh convergence failed.');
            end
            a.pitch=[];
            if a.applicable
                % Bending inclines the surface normal; force projected onto the original
                % plane is reduced. This finite-incidence secant is a diagnostic only.
                a.effective_CNalpha=input.fin_set_CNalpha_per_rad*a.finite_angle_force_ratio;
                a.cp_m=(2*g.nose_length/1000*2/3+a.effective_CNalpha*input.fin_cp_m)/(2+a.effective_CNalpha);
                % The true zero-incidence derivative does not include cos(beta)^2, a
                % second-order change. Use the linear torsion derivative for local pitch.
                cn=input.fin_set_CNalpha_per_rad*a.linear_torsion_gain;
                cp=(2*g.nose_length/1000*2/3+cn*input.fin_cp_m)/(2+cn);
                m=input.design.dry_mass_kg+input.design.payload_mass_kg;
                J=m*(g.overall/1000)^2/12;
                arm=cp-input.assembly.loaded_cg_mm/1000;
                K=q*pi*(g.body_diameter/2000)^2*(cn+2)*arm;
                a.wet_margin_m=cp-input.assembly.wet_cg_mm/1000;
                if K>0
                    w=sqrt(K/J); A=w*[0 1;-1 -2*p.pitch_zeta]; P=lyap(A',eye(2));
                    S=-(A'*P+P*A); rate=min(eig(S,P))/2;
                    assert(norm(A'*P+P*A+eye(2),'fro')<1e-9 && min(eig(P))>0);
                    a.pitch=struct('dry_local_decay_per_s',rate,'max_real_pole',max(real(eig(A))), ...
                        'assumed_pitch_zeta',p.pitch_zeta,'wet_static_margin_m',a.wet_margin_m, ...
                        'status','conditional_local_only');
                end
            end
            if isempty(cases), cases=a;
            else, cases(ncase)=orderfields(a,cases); end %#ok<AGROW>
        end
    end
end
r.cases=cases;
r.gates=struct('max_rotation_deg',p.max_rotation_deg,'max_deflection_span_fraction',p.max_deflection_span_fraction, ...
    'divergence_pressure_fraction_limit',0.9,'whole_flight_stability','not_assessed');
% Verify the same integration against the closed-form uniform cantilever.
x=linspace(0,1,1601)'; EI=3; loadNpm=2;
u=cumtrapz(x,cumtrapz(x,loadNpm*(1-x).^2/(2*EI)));
assert(abs(u(end)-loadNpm/(8*EI))<1e-7);
fig=figure('Visible','off','Color','white','Position',[20 20 1100 740]);clean=onCleanup(@()close(fig)); %#ok<NASGU>
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');
tiledlayout(2,2,'TileSpacing','compact');
for qindex=1:2
    nexttile; hold on
    for j=1:numel(names)
        a=cases((j-1)*6+(qindex-1)*3+2);
        plot(a.span_m*1000,a.deflection_m*1000,'LineWidth',2,'DisplayName',names(j));
    end
    yline(g.fin_span*p.max_deflection_span_fraction,'k--','微小変形の仮の判定線');
    grid on; legend('Location','northwest','Interpreter','none'); xlabel('根元から (mm)');ylabel('面外変位 (mm)');
    title(sprintf('動圧 %.0f Pa・迎角 %.0f°・ねじり偏心なし',qvalues(qindex),p.incidence_deg));
end
nexttile; hold on
for j=1:numel(names)
    a=cases((j-1)*6+6);
    plot(a.span_m*1000,a.twist_deg,'LineWidth',2,'DisplayName',names(j));
end
yline(p.max_rotation_deg,'k--'); grid on; xlabel('根元から (mm)');ylabel('ねじり角 (°)');
title('最大動圧・偏心 +0.25 弦長 の仮定'); legend('Location','northwest','Interpreter','none');
nexttile; axis off
text(0,.9,{'剛性・接着・取付ばね・空力の作用点は仮定'; '微小変形の範囲を外れたケースは姿勢解析を保留'; ...
    '温度 → 剛性 → 変形 → 空力係数 → 局所安定性'; '指数減衰は乾燥・固定流れ・仮の減衰比での結果'; ...
    '全飛行の安定性、フラッター、材料破壊は未判定'},'FontSize',12,'VerticalAlignment','top');
exportgraphics(fig,fullfile(outDir,'fin-coupling.png'),'Resolution',150);
end

function a=solveFin(input,p,q,offset,factor,rootFactor,N)
g=input.assembly.dimensions_mm; L=g.fin_span/1000; x=linspace(0,L,N+1)'; dx=L/N;
c=(g.fin_root+(g.fin_tip-g.fin_root)*x/L)/1000; t=p.thickness_m;
% Two fins are active in the selected pitch plane; the supplied CN covers the full set.
wts=ones(N+1,1)*dx;wts([1,end])=dx/2;
liftSlope=input.fin_set_CNalpha_per_rad/2*pi*(g.body_diameter/2000)^2*c.*wts/sum(c.*wts);
E=p.E_pa*factor; G=E/(2*(1+p.nu)); J=c*t^3/3;
K=zeros(N+1); for k=1:N
    ids=k:k+1; K(ids,ids)=K(ids,ids)+G*mean(J(ids))/dx*[1 -1;-1 1];
end
K(1,1)=K(1,1)+p.root_twist_stiffness_nm_rad*rootFactor;
B=diag(offset*c.*liftSlope);
qdiv=Inf;
if offset>0, qdiv=min(eig(K,B)); end
alpha=deg2rad(p.incidence_deg); twist=(K-q*B)\(q*B*ones(N+1,1)*alpha);
% Algebraic continuation beyond divergence is not a stable static displacement.
staticExists=q<qdiv;
if ~staticExists,twist(:)=NaN;end
loads=q*liftSlope.*(alpha+twist); moment=zeros(N+1,1);
for k=1:N+1, moment(k)=sum(loads(k:end).*(x(k:end)-x(k)));end
I=c*t^3/12; beta0=moment(1)/(p.root_bend_stiffness_nm_rad*rootFactor);
slope=beta0+cumtrapz(x,moment./(E*I)); deflection=cumtrapz(x,slope);
stress=moment.*(t/2)./I;
% Independent plies: same total thickness but 1/4 EI, and each outer ply is t/4
% from its own neutral axis. The stress is twice the fully bonded value.
if factor==0.25, stress=stress*2;end
linearGain=sum(loads)/(q*sum(liftSlope)*alpha);
projectedGain=sum(loads.*cos(slope).^2)/(q*sum(liftSlope)*alpha);
rotation=max([abs(slope);abs(twist)]);
applicable=abs(deflection(end))/L<=p.max_deflection_span_fraction && ...
    rad2deg(rotation)<=p.max_rotation_deg && q<0.9*qdiv;
reason='within_provisional_small_deformation_limits';
if ~staticExists,reason='static_divergence_in_assumed_torsion_model';
elseif ~applicable,reason='small_deformation_or_divergence_margin_exceeded';end
a=struct('dynamic_pressure_pa',q,'offset_chord_fraction',offset,'stiffness_ratio',factor, ...
    'span_m',x,'deflection_m',deflection,'twist_deg',rad2deg(twist), ...
    'tip_deflection_m',deflection(end),'max_rotation_deg',rad2deg(rotation), ...
    'root_bending_stress_MPa',stress(1)/1e6,'root_force_n',sum(loads), ...
    'root_bending_moment_nm',moment(1),'average_tab_shear_pa',sum(loads)/(g.fin_root*g.fin_tab/1e6), ...
    'divergence_q_pa',qdiv,'linear_torsion_gain',linearGain, ...
    'finite_angle_force_ratio',projectedGain,'applicable',applicable, ...
    'static_equilibrium_exists',staticExists,'applicability_reason',reason, ...
    'effective_CNalpha',NaN,'cp_m',NaN,'wet_margin_m',NaN);
end
