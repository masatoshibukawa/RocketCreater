function result = bottle_lyapunov(designFile, outDir)
% Conditional stability of two isolated perturbation models, not flight qualification.
% Example from scenarios/: bottle_lyapunov('../output/egg-hybrid/design.json','../output/stability')
arguments
    designFile (1,1) string
    outDir (1,1) string
end
design = jsondecode(fileread(designFile));
assert(strcmp(design.tier,'bottle') && design.has_fins, 'Expected a finned bottle design.');
assert(all(isfinite([design.dry_mass_kg design.payload_mass_kg design.bottle_volume_m3])) ...
    && all([design.dry_mass_kg design.payload_mass_kg design.bottle_volume_m3] > 0));
result.design = design;
result.scope = 'Unforced small pitch perturbation and axial payload vibration, separately.';
result.whole_flight = 'not_assessed';

% Dry coast, fixed reference flow direction; angle and angle rate only.
% Positive arm = CP aft of CG. Pitch inertia uses a slender rod surrogate.
p = struct('speed_ref_mps',15,'speed_band_mps',[14 16],'air_density_kg_m3',1.2, ...
    'length_m',0.40,'diameter_m',0.09*(design.bottle_volume_m3/0.0015)^(1/3), ...
    'normal_force_slope_per_rad',3,'cp_aft_of_cg_m',0.04,'damping_ratio_at_ref',0.15);
J = (design.dry_mass_kg+design.payload_mass_kg)*p.length_m^2/12;
K = 0.5*p.air_density_kg_m3*p.speed_ref_mps^2*pi*p.diameter_m^2/4 ...
    *p.normal_force_slope_per_rad*p.cp_aft_of_cg_m;
w = sqrt(K/J); z = p.damping_ratio_at_ref;
% x = [pitch error; pitch rate / w]. The restoring slope scales with U^2
% and the assumed rate damping with U. w is FIXED, including during speed changes.
A = @(stiffRatio,dampRatio) w*[0 1; -stiffRatio -2*z*dampRatio];
A0 = A(1,1);
P = lyap(A0',eye(2)); P = (P+P')/2;
assert(min(eig(P)) > 0 && norm(A0'*P + P*A0 + eye(2),'fro') < 1e-9);
r = p.speed_band_mps/p.speed_ref_mps;
rates = zeros(2);
for i = 1:2
    for j = 1:2
        % Four vertices enclose every (U^2/Uref^2,U/Uref). S is affine
        % in these two coordinates, so positivity extends to the full box.
        rates(i,j) = decayRate(A(r(i)^2,r(j)),P);
    end
end
a = min(rates,[],'all');
assert(a > 0, 'Common P is inconclusive on this band; this is not proof of instability.');
result.pitch = struct('assumptions',p,'assumed_inertia_kg_m2',J,'w_ref_rad_s',w, ...
    'P',P,'A_ref',A0,'corner_amplitude_rates_per_s',rates, ...
    'uniform_amplitude_rate_per_s',a,'norm_prefactor',sqrt(cond(P)), ...
    'reversed_arm_growth_per_s',max(real(eig(A(-1,1)))));
assert(result.pitch.reversed_arm_growth_per_s > 0);
% In the undamped case x'*x is conserved, including nonzero initial states.
assert(norm(A(1,0)'+A(1,0),'fro') < 1e-10);

% Two axial DOFs on a fixed base: support and payload. The support is part
% of dry mass, not additional flight mass. Uncoupled modal viscous damping.
M = diag([0.020 design.payload_mass_kg]);
kWall = 2500; kPad = 600;
Ks = [kWall+kPad -kPad; -kPad kPad];
omega = sort(sqrt(eig(Ks,M)));
result.mount = struct('support_mass_kg',M(1,1),'wall_stiffness_n_m',kWall, ...
    'pad_stiffness_n_m',kPad,'mode_hz',omega'/(2*pi), ...
    'requirement','sqrt(total free-vibration energy) <= 10% of initial after 0.5 s');
t = 0:0.002:0.5;
zetas = [0 0.02 0.06];
gain = zeros(numel(zetas),numel(t));
for n = 1:numel(zetas)
    d = zetas(n);
    % For mass-normalized modal coordinates, y_i=[omega_i*q_i; qdot_i],
    % hence ||y||^2=2E. In this metric a bound on every initial phase is meaningful.
    B = [0 1; -1 -2*d];
    Am = blkdiag(omega(1)*B,omega(2)*B);
    H = [1 d; d 1];
    Pm = blkdiag(H,H);
    rate = decayRate(Am,Pm);
    assert(min(eig(Pm)) > 0 && abs(rate-d*omega(1)) < 1e-8);
    prefactor = sqrt(cond(Pm));
    bound = prefactor*exp(-rate*t(end));
    for j = 1:numel(t)
        gain(n,j) = norm(expm(Am*t(j)),2);
    end
    assert(all(gain(n,:) <= prefactor*exp(-rate*t) + 1e-10));
    result.mount.cases(n) = struct('assumed_modal_damping_ratio',d,'P',Pm,'A',Am, ...
        'amplitude_rate_per_s',rate,'norm_prefactor',prefactor, ...
        'bound_at_0p5s',bound,'worst_gain_at_0p5s',gain(n,end), ...
        'settling_certified',bound <= 0.10);
end
assert(abs(gain(1,end)-1) < 1e-9, 'Undamped energy must be conserved.');
if abs(design.payload_mass_kg-0.06) < 1e-12
    assert(gain(2,end) > 0.10 && bound < 0.10, 'Reference 60 g regression failed.');
end
if ~isfolder(outDir), mkdir(outDir); end
path = fullfile(outDir,'lyapunov.json');
fid = fopen(path,'w','n','UTF-8'); assert(fid ~= -1,'Cannot open output file.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(result,PrettyPrint=true)); clear cleanup

fig = figure('Visible','off','Color','white','Position',[10 10 940 365]);
cleanupFig = onCleanup(@() close(fig));
tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');
ax = nexttile; hold(ax,'on'); ax.FontName = 'Meiryo';
colororder(ax,[0.05 0.39 0.50; 0.40 0.42 0.43; 0.78 0.23 0.12]);
for pair = [1 1; 1 0; -1 1]'
    pitchGain = arrayfun(@(s) norm(expm(A(pair(1),pair(2))*s),2),t);
    semilogy(ax,t,pitchGain,'LineWidth',2);
end
set(ax,'YScale','log'); grid(ax,'on'); title(ax,'機体のピッチ（仮定した対気速度 15 m/s）');
xlabel(ax,'時間 (s)'); ylabel(ax,'初期の姿勢ずれに対する最大倍率');
legend(ax,{'復元力と減衰あり','減衰なし','復元力が逆向き'},'Location','northwest');
ax = nexttile; hold(ax,'on'); ax.FontName = 'Meiryo';
colororder(ax,[0.40 0.42 0.43; 0.85 0.45 0.07; 0.05 0.39 0.50]);
for n = 1:numel(zetas), semilogy(ax,t,gain(n,:),'LineWidth',2); end
set(ax,'YScale','log'); yline(ax,0.10,'k--','10%'); grid(ax,'on');
title(ax,sprintf('搭載部の自由振動（搭載物 %.0f g）',design.payload_mass_kg*1000));
xlabel(ax,'時間 (s)'); ylabel(ax,'振動エネルギーの平方根の最大倍率');
legend(ax,{'減衰なし','減衰比 2%','減衰比 6%'},'Location','southwest');
exportgraphics(fig,fullfile(outDir,'lyapunov.png'),'Resolution',150);
fprintf('Pitch uniform rate %.4f /s, reversed pole +%.4f /s.\n', ...
    a,result.pitch.reversed_arm_growth_per_s);
fprintf('Mount rates /s: %s; bounds at 0.5 s: %s; exact gains: %s\n', ...
    mat2str([result.mount.cases.amplitude_rate_per_s],4), ...
    mat2str([result.mount.cases.bound_at_0p5s],4),mat2str(gain(:,end)',4));
end

function a = decayRate(A,P)
% dV/dt <= -2*a*V => ||x(t)|| <= sqrt(cond(P))*exp(-a*t)*||x(0)||.
S = -(A'*P+P*A); S = (S+S')/2;
a = min(eig(S,P))/2;
end
