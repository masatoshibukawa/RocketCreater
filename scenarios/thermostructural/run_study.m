function result=run_study(inputFile,outDir)
% Reproducible conditional hierarchy. MATLAB + Control System + PDE toolboxes.
arguments
    inputFile (1,1) string
    outDir (1,1) string
end
here=fileparts(mfilename('fullpath'));
cfg=jsondecode(fileread(fullfile(here,'assumptions.json')));input=jsondecode(fileread(inputFile));
assert(cfg.provisional && input.design.payload_mass_kg>0);
if ~isfolder(outDir),mkdir(outDir);end
savePart('run-status',struct('state','running'));
result.physical_status='not_qualified';result.source_sha256=input.source_sha256;
result.assumptions=cfg;
fprintf('Thermal histories...\n'); result.thermal=thermal_response(input,cfg,outDir);savePart('thermal',result.thermal);
fprintf('Fin bending, torsion and gated pitch...\n');result.fin=fin_response(input,cfg,result.thermal,outDir);savePart('fin',result.fin);
fprintf('Payload shock and travel limits...\n');result.payload=payload_response(input,cfg,outDir);savePart('payload',result.payload);
fprintf('Body membrane and sleeve loads...\n');result.body=body_response(input,cfg,result.payload,result.thermal,outDir);savePart('body',result.body);
fprintf('Collar 3D FEM...\n');result.collar=collar_fem(input,cfg,result.payload,result.thermal,outDir);savePart('collar',result.collar);
result.harness=struct('low_layer','material_and_joint_data_provisional', ...
    'fin_cases_outside_applicability',sum(~[result.fin.cases.applicable]), ...
    'payload_cases_reaching_stop',sum(~[result.payload.cases.linear_response_applicable]), ...
    'strength_allowables','missing','whole_flight_stability','not_assessed','qualification','blocked');
savePart('results',result);savePart('run-status',struct('state','complete'));
fprintf('Complete. Physical qualification remains unresolved.\n');
    function savePart(name,value)
        fid=fopen(fullfile(outDir,name+".json"),'w','n','UTF-8');assert(fid~=-1);clean=onCleanup(@()fclose(fid)); %#ok<NASGU>
        fprintf(fid,'%s\n',jsonencode(value,PrettyPrint=true));
    end
end
