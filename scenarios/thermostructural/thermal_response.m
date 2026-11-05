function r = thermal_response(input, cfg, outDir)
% Conditional thermal histories. Gas -> wall is a one-way imposed-temperature model.
p = cfg.thermal; d = input.design; g = input.assembly.dimensions_mm;
r.provisional = true;
r.scope = 'Water-expulsion cooling and a separate unpressurised sun-wait scenario.';
for j = 1:numel(p.polytropic_exponents)
    n = p.polytropic_exponents(j);
    [t,y] = cooling(input,p,n,12);
    [~,yf] = cooling(input,p,n,24);
    gas = (p.gas_initial_C+273.15)*(d.bottle_volume_m3*(1-d.water_fill_frac)./y(:,1)).^(n-1)-273.15;
    diffK = abs(mean(y(end,2:end))-mean(yf(end,2:end)));
    assert(diffK < 0.01,'Through-thickness cooling grid did not converge.');
    r.cooling(j) = struct('polytropic_exponent',n,'water_end_s',t(end), ...
        'gas_end_C',gas(end),'wall_inner_end_C',y(end,2),'wall_outer_end_C',y(end,end), ...
        'wall_mean_end_C',mean(y(end,2:end)),'refinement_delta_K',diffK, ...
        'time_s',t,'gas_C',gas,'wall_inner_C',y(:,2),'wall_outer_C',y(:,end));
end
% Three nodes in payload bay, plus an independently exposed fin.
% SIMPLIFICATION: uniform nodes, side-on sun, radiation to ambient, no internal electronics.
D=g.body_diameter/1000; L=g.egg_bay_length/1000;
areaSkin=pi*D*L; projSkin=D*L;
areaFin=(g.fin_root+g.fin_tip)*g.fin_span/2e6;
padG=p.pad_k_w_m_k*p.pad_area_m2/(g.padding/1000);
C=[p.skin_mass_kg*p.skin_cp_j_kg_k; input.assembly.print_parts.pair_solid_pla_g/1000*cfg.collar.cp_j_kg_k; ...
    d.payload_mass_kg*p.payload_cp_j_kg_k; p.exposed_fin_mass_kg*p.fin_cp_j_kg_k];
for j=1:numel(p.absorptivities)
    absorp=p.absorptivities(j); ts=linspace(0,p.wait_s,601);
    [t,y]=ode15s(@rates,ts,ones(4,1)*p.initial_C,odeset('RelTol',1e-8,'AbsTol',1e-9));
    % Repeat with no heating or temperature difference: exact equilibrium must remain.
    r.sun(j)=struct('absorptivity',absorp,'time_s',t,'skin_C',y(:,1), ...
        'mount_C',y(:,2),'payload_C',y(:,3),'fin_C',y(:,4));
end
eq=ones(4,1)*p.ambient_C; absorp=0;
assert(norm(rates(0,eq))<1e-12,'Uniform thermal equilibrium was not preserved.');
r.hot_mount_C=r.sun(end).mount_C(end);
r.hot_fin_C=r.sun(end).fin_C(end);
frac=min(1,max(0,(r.hot_fin_C-cfg.fin.softening_begin_C)/(cfg.fin.softening_end_C-cfg.fin.softening_begin_C)));
r.assumed_warm_fin_stiffness_ratio=1-frac*(1-cfg.fin.warm_stiffness_ratio);
r.aerodynamic_stagnation_rise_K=input.max_speed_mps^2/(2*1005);
% Free expansion mismatch, not stress: real contact may slip or open.
r.mount_vs_sleeve_radial_mismatch_mm=1000*input.assembly.print_parts.collar_outer_mm/2000* ...
    (cfg.collar.CTE_per_K*(r.hot_mount_C-cfg.collar.reference_C)- ...
    cfg.body.CTE_per_K*(r.sun(end).skin_C(end)-cfg.collar.reference_C));
fig=figure('Visible','off','Color','white','Position',[20 20 1100 750]);
clean=onCleanup(@()close(fig)); %#ok<NASGU>
set(fig,'defaultAxesFontName','Meiryo','defaultTextFontName','Meiryo');
tiledlayout(2,2,'TileSpacing','compact');
nexttile; hold on
for j=1:numel(r.cooling)
    z=r.cooling(j); plot(z.time_s,z.gas_C,'LineWidth',2,'DisplayName',sprintf('気体 n = %.1f',z.polytropic_exponent));
    plot(z.time_s,z.wall_inner_C,'--','LineWidth',2,'DisplayName',sprintf('内壁 n = %.1f',z.polytropic_exponent));
end
grid on; legend('Location','southwest'); xlabel('水噴射中の時間 (s)'); ylabel('温度 (°C)'); title('気体の冷却と壁温度を区別');
nexttile; hold on
for j=1:numel(r.sun)
    z=r.sun(j); plot(z.time_s/60,z.skin_C,'LineWidth',2,'DisplayName',sprintf('外装 吸収率 %.1f',z.absorptivity));
    plot(z.time_s/60,z.payload_C,'--','LineWidth',2,'DisplayName',sprintf('搭載物 吸収率 %.1f',z.absorptivity));
end
grid on; legend('Location','northwest'); xlabel('日なたでの待機時間 (min)'); ylabel('温度 (°C)'); title('未加圧・気温 35°C・日射 800 W/m² の仮定');
nexttile; z=r.sun(end); plot(z.time_s/60,[z.skin_C,z.mount_C,z.payload_C,z.fin_C],'LineWidth',2);
grid on; legend('外装','保持リング','搭載物','露出フィン','Location','northwest'); xlabel('時間 (min)'); ylabel('温度 (°C)'); title('吸収率 0.8 の温度を構造解析へ渡す');
nexttile; axis off
text(0,0.9,{'材料物性・熱伝達率・日射条件は仮定'; '冷却は水噴射終了まで（空気だけの噴出は対象外）'; ...
    '日なたの例は未加圧。内圧への温度フィードバックは未解析'; '温度からの剛性変化も仮の感度モデル'; ...
    sprintf('飛行速度による最大の全温上昇 %.2f K',r.aerodynamic_stagnation_rise_K)},'FontSize',12,'VerticalAlignment','top');
exportgraphics(fig,fullfile(outDir,'thermal.png'),'Resolution',150);
    function dy=rates(~,y)
        rad=@(T) p.emissivity*5.670374419e-8*((T+273.15)^4-(p.ambient_C+273.15)^4);
        Qskin=absorp*p.solar_w_m2*projSkin-areaSkin*(p.outside_h_w_m2_k*(y(1)-p.ambient_C)+rad(y(1)));
        Qfin=absorp*p.solar_w_m2*areaFin-2*areaFin*(p.outside_h_w_m2_k*(y(4)-p.ambient_C)+rad(y(4)));
        Qsm=padG*(y(1)-y(2)); Qmp=p.mount_payload_conductance_w_k*(y(2)-y(3));
        dy=[Qskin-Qsm;Qsm-Qmp;Qmp;Qfin]./C;
    end
end

function [t,y]=cooling(input,p,n,N)
d=input.design; V0=d.bottle_volume_m3*(1-d.water_fill_frac); p0=input.ambient_pressure_pa+d.initial_gauge_pressure_pa;
dx=p.wall_thickness_m/N; c=p.wall_rho_kg_m3*p.wall_cp_j_kg_k*dx;
G=p.wall_k_w_m_k/dx; hi=1/(1/p.inside_h_w_m2_k+dx/(2*p.wall_k_w_m_k));
ho=1/(1/p.outside_h_w_m2_k+dx/(2*p.wall_k_w_m_k));
[t,y]=ode15s(@rhs,[0 5],[V0;ones(N,1)*p.gas_initial_C], ...
    odeset('RelTol',1e-9,'AbsTol',1e-10,'Events',@done,'MaxStep',0.002));
assert(abs(y(end,1)-d.bottle_volume_m3)<1e-10,'Water was not exhausted.');
    function dy=rhs(~,y)
        V=y(1); T=y(2:end); pg=p0*(V0/V)^n;
        Tg=(p.gas_initial_C+273.15)*(V0/V)^(n-1)-273.15;
        flux=G*diff(T); q=[hi*(Tg-T(1));flux;ho*(T(end)-p.gas_initial_C)];
        % Interior flux is positive toward the previous node, so assemble explicitly.
        net=[hi*(Tg-T(1))+flux(1);diff(flux);-flux(end)+ho*(p.gas_initial_C-T(end))];
        assert(isfinite(sum(q)));
        dv=pi*(d.nozzle_diameter_m/2)^2*sqrt(2*max(pg-input.ambient_pressure_pa,0)/1000);
        dy=[dv;net/c];
    end
    function [v,term,dir]=done(~,y)
        v=y(1)-d.bottle_volume_m3;term=1;dir=1;
    end
end
