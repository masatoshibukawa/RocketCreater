"""Reusable Blender stage libraries; no rocket, liquid, CAD or trajectory is stored here."""

from pathlib import Path

import bpy

from rocketwright.agent.video_cache import MediaCache, digest, file_sha


def stage(job, cache_root, appearance, template, *, force_build=False):
    identity = digest(
        dict(
            schema=1,
            template=template["id"],
            style=job["plan"].get("style"),
            assets=job.get("appearance_sha256"),
            blender=bpy.app.version_string,
            code=file_sha(__file__),
            appearance=file_sha(appearance.__file__),
        )
    )
    cache = MediaCache(cache_root)
    directory = cache.directory("stages", identity)
    library = directory / "stage.blend"
    files = cache.manifest("stages", identity)
    reused = False
    if (
        not force_build
        and library.is_file()
        and files.get("stage.blend", {}).get("sha256") == file_sha(library)
    ):
        with bpy.data.libraries.load(str(library)) as (source, target):
            target.collections = ["Reusable stage"]
            target.worlds = ["Stage design world", "Stage launch world"]
        collection = target.collections[0]
        bpy.context.scene.collection.children.link(collection)
        reused = True
    else:
        collection = bpy.data.collections.new("Reusable stage")
        bpy.context.scene.collection.children.link(collection)

        def adopt(obj, name):
            obj.name = name
            for owner in list(obj.users_collection):
                owner.objects.unlink(obj)
            collection.objects.link(obj)
            return obj

        photo = job["plan"].get("style") == "photographic"
        bpy.ops.mesh.primitive_plane_add(size=400)
        ground = adopt(bpy.context.object, "Stage ground")
        ground.location.z = -0.01
        ground.data.materials.append(
            appearance.asphalt(Path(job["asset_directory"]))
            if photo
            else appearance.material("Ground", (0.055, 0.065, 0.07))
        )
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.78))
        bench = adopt(bpy.context.object, "Illustrative workbench")
        bench.dimensions = (2.6, 1.7, 0.08) if template["id"] == "large" else (1.8, 1.15, 0.08)
        bench.data.materials.append(
            appearance.material("Workshop bench", (0.22, 0.25, 0.27), 0.3, metallic=0.7)
        )
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.821))
        mat = adopt(bpy.context.object, "Cutting mat")
        mat.dimensions = (0.9, 0.7, 0.002)
        mat.data.materials.append(appearance.material("Cutting mat", (0.025, 0.07, 0.061), 0.8))
        bpy.ops.object.light_add(type="AREA", location=(2, -2, 4))
        lamp = adopt(bpy.context.object, "Stage softbox")
        lamp.data.energy, lamp.data.shape, lamp.data.size = 350, "DISK", 4
        bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
        adopt(bpy.context.object, "Stage daylight").data.energy = 1.5
        bpy.ops.object.camera_add()
        camera = adopt(bpy.context.object, "Stage camera")
        camera.data.lens = 45
        worlds = []
        for mode in ("design", "launch"):
            if photo:
                appearance.photo_world(mode, job["asset_directory"])
                world = bpy.context.scene.world
            else:
                world = bpy.data.worlds.new("Engineering world")
                world.color = (0.12, 0.15, 0.2)
            world.name = "Stage " + mode + " world"
            worlds.append(world)
        for image in bpy.data.images:
            if image.source == "FILE" and not image.packed_file:
                image.pack()
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / "stage-building.blend"
        bpy.data.libraries.write(str(temp), {collection, *worlds}, fake_user=True, compress=True)
        cache.store("stages", identity, "stage.blend", temp)
        temp.unlink()
    objects = {obj.name.split(".")[0]: obj for obj in collection.objects}
    # Locate the newly appended worlds even if the caller has similarly named worlds.
    worlds = target.worlds if reused else worlds
    result = dict(
        ground=objects["Stage ground"],
        bench=objects["Illustrative workbench"],
        mat=objects["Cutting mat"],
        camera=objects["Stage camera"],
        worlds=dict(zip(("design", "launch"), worlds, strict=True)),
    )
    result["camera"].data.dof.use_dof = job["plan"].get("style") == "photographic"
    result["camera"].data.dof.aperture_fstop = template["fstop"]
    bpy.context.scene.camera = result["camera"]
    return result, dict(
        template=template, identity=identity, reused=reused, stage_sha256=file_sha(library)
    )
