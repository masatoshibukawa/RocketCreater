function r = payload_response(input,cfg,outDir)
% Two axial DOFs, driven by proper base acceleration. No fracture/contact law.
p=cfg.mount; m=input.design.payload_mass_kg;
M=diag([p.support_mass_kg,m]); K=[p.wall_stiffness_n_m+p.pad_stiffness_n_m,-p.pad_stiffness_n_m;-p.pad_stiffness_n_m,p.pad_stiffness_n_m];
[V,D]=eig(K,M); w=sqrt(diag(D));
for k=1:2,V(:,k)=V(:,k)/sqrt(V(:,k)'*M*V(:,k));end
C=M*V*diag(2*p.modal_zeta*w)*V'*M;
assert(norm(V'*M*V-eye(2),'fro')<1e-10);
r.provisional=true; r.mode_hz=w/(2*pi);r.scope='Axial linear mount with assumed modal damping; stop impacts are gated.';
cases={}; count=0;
% Air impulse is redistributed into finite pulses, not differentiated from velocity.
for tau=p.air_pulse_durations_s'
    count=count+1; t0=input.water_end_s; dv=input.air_impulse_ns/(input.design.dry_mass_kg+m);
    tflight=input.trace.time_s; aflight=input.trace.proper_accel_mps2;
    iw=tflight<t0; tw=tflight(iw); aw=aflight(iw);
    drive=@(t) launch(t,tw,aw,t0,tau,dv);
    cases{count}=oneCase('launch',tau,NaN,t0+tau+0.5,drive,9.80665,2e-4); %#ok<AGROW>
end
for stop=p.landing_stop_distances_m'
    count=count+1; dv=input.landing_speed_mps; tau=2*stop/dv;
    drive=@(t) 9.80665+pulse(t,0.02,tau,dv);
    cases{count}=oneCase('landing',tau,stop,tau+0.6,drive,9.80665,2e-4); %#ok<AGROW>
end
for tau=p.opening_durations_s'
    count=count+1; drive=@(t) 9.80665+pulse(t,0.02,tau,p.opening_delta_v_mps);
    cases{count}=oneCase('opening_sensitivity',tau,NaN,tau+0.6,drive,9.80665,2e-4); %#ok<AGROW>
end
cases=[cases{:}];r.cases=cases;
% Time refinement for the shortest landing pulse and conservation of pulse impulse.
stop=p.landing_stop_distances_m(1);dv=input.landing_speed_mps;tau=2*stop/dv;
drive=@(t)9.80665+pulse(t,0.02,tau,dv);
fine=oneCase('refinement',tau,stop,tau+0.6,drive,9.80665,1e-4);
coarse=cases(numel(p.air_pulse_durations_s)+1);
r.refinement_relative=abs(fine.peak_pad_travel_mm-coarse.peak_pad_travel_mm)/fine.peak_pad_travel_mm;
assert(r.refinement_relative<0.01);
assert(abs(integral(@(t)pulse(t,0,tau,dv),0,tau)-dv)<1e-9);
% If a model reaches its travel limit, its later force prediction is invalid.
% Use separately labelled rigid-body inertial demand for a collar load scenario.
r.collar_axial_load_scenario_n=max([cases.peak_base_proper_mps2])*m;
r.collar_load_basis='Payload mass times imposed peak proper acceleration; not a bound on contact force.';
r.whole_body_axial_load_scenario_n=max([cases.peak_base_proper_mps2])*(input.design.dry_mass_kg+m);
r.stroke_available_mm=p.available_stroke_m*1000;
fig=figure('Visible','off','Color','white','Position',[20 20 1100 730]);clean=onCleanup(@()close(fig)); %#ok<NASGU>
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');tiledlayout(2,2,'TileSpacing','compact');
for type=["launch","landing"]
    nexttile; hold on
    rows=cases(strcmp({cases.kind},type));
    for a=rows
        before=isnan(a.first_travel_limit_s) | a.time_s<=a.first_travel_limit_s;
        line=plot(a.time_s(before),a.pad_travel_mm(before),'LineWidth',1.8,'DisplayName',sprintf('パルス %.1f ms',a.duration_s*1000));
        plot(a.time_s(~before),a.pad_travel_mm(~before),'--','Color',line.Color,'LineWidth',1.2,'HandleVisibility','off');
    end
    yline(p.available_stroke_m*1000,'k--','仮の可動域','HandleVisibility','off'); yline(-p.available_stroke_m*1000,'k--','HandleVisibility','off');
    grid on; legend('Location','best');xlabel('時間 (s)');ylabel('搭載物と支持部の相対変位 (mm)');
    if type=="launch",title('発射・破線部分は可動域を超えた外挿');else,title('着地・破線部分は可動域を超えた外挿');end
end
nexttile; rows=cases(strcmp({cases.kind},'landing'));
plot([rows.stop_distance_m]*1000,[rows.peak_base_proper_mps2]/9.80665,'o-','LineWidth',2);
grid on; xlabel('胴体が停止する距離 (mm)');ylabel('胴体への最大荷重係数 (g)');title('下降速度だけでは衝撃を判断できない');
nexttile;axis off
text(0,.9,{sprintf('搭載部の仮の固有振動数 %.1f / %.1f Hz',r.mode_hz); ...
    '可動域を超えたら接触・底付き解析が必要'; '超過後の線形計算値を実物の荷重に採用しない'; ...
    '空気噴出時間・開傘時間・停止距離は未測定'; '卵の破損・保持具の抜け・接着の剥離は未判定'},'FontSize',12,'VerticalAlignment','top');
exportgraphics(fig,fullfile(outDir,'payload.png'),'Resolution',150);
    function a=oneCase(kind,tau,stop,T,drive,initialProper,dt)
        z0=-K\(M*ones(2,1)*initialProper);
        ts=unique([0:dt:T,T]);
        [t,z]=ode45(@(t,z)[z(3:4);M\(-C*z(3:4)-K*z(1:2))-ones(2,1)*drive(t)], ...
            ts,[z0;0;0],odeset('RelTol',1e-8,'AbsTol',1e-10,'MaxStep',min(dt,tau/30)));
        pad=z(:,2)-z(:,1); proper=arrayfun(drive,t);
        force=-(K*z(:,1:2)'+C*z(:,3:4)');
        payloadForce=force(2,:); wallReaction=sum(force,1);
        hit=find(abs(pad)>=p.available_stroke_m,1);
        firstHit=NaN;if ~isempty(hit),firstHit=t(hit);end
        a=struct('kind',kind,'duration_s',tau,'stop_distance_m',stop,'time_s',t, ...
            'pad_travel_mm',pad*1000,'peak_pad_travel_mm',max(abs(pad))*1000, ...
            'peak_base_proper_mps2',max(abs(proper)), ...
            'linear_peak_payload_force_n',max(abs(payloadForce)), ...
            'linear_peak_wall_reaction_n',max(abs(wallReaction)), ...
            'first_travel_limit_s',firstHit,'linear_response_applicable',isempty(hit), ...
            'fracture_status','unknown_without_allowable_and_contact_model');
    end
end

function a=launch(t,tw,aw,t0,tau,dv)
if t<t0,a=interp1(tw,aw,min(t,tw(end)),'linear');
else,a=pulse(t,t0,tau,dv);end
end

function a=pulse(t,t0,tau,dv)
u=(t-t0)/tau; a=pi*dv/(2*tau)*sin(pi*min(1,max(0,u))).*(u>=0 & u<=1);
end
