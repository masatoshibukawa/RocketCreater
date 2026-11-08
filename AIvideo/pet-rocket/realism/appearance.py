"""Shared photographic lighting and material recipes from the PET v2 production.

Environment maps and asphalt: Poly Haven, CC0; see asset-manifest.json.
No scene geometry, frozen CAD or flight trajectory is loaded by this module.
"""

from pathlib import Path

import bpy


def material(name, color, roughness=0.3, metallic=0, transmission=0, ior=1.45):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    for key, value in {
        "Base Color": (*color, 1),
        "Roughness": roughness,
        "Metallic": metallic,
        "Transmission Weight": transmission,
        "IOR": ior,
    }.items():
        shader.inputs[key].default_value = value
    return result


def photo_world(film, cache):
    world = bpy.data.worlds.new("Photo environment / Poly Haven CC0")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(
        str(Path(cache) / ("workshop.exr" if film == "design" else "outdoor.exr"))
    )
    tex = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = 1.3 if film == "design" else 2.65
    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], nodes["Background"].inputs["Color"])
    nodes["Background"].inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world


<<<<<<< HEAD
def surface_detail(mat, layered=False, roughness_range=None):
=======
def surface_detail(mat, layered=False):
>>>>>>> origin/checkpoint/video-worktree-20261106
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    tex = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1500
    links.new(tex.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0
    ramp.inputs["From Max"].default_value = 1
<<<<<<< HEAD
    low, high = roughness_range or ((0.23, 0.38) if layered else (0.022, 0.075))
    ramp.inputs["To Min"].default_value = low
    ramp.inputs["To Max"].default_value = high
=======
    ramp.inputs["To Min"].default_value = 0.23 if layered else 0.022
    ramp.inputs["To Max"].default_value = 0.38 if layered else 0.075
>>>>>>> origin/checkpoint/video-worktree-20261106
    links.new(noise.outputs["Fac"], ramp.inputs["Value"])
    links.new(ramp.outputs["Result"], shader.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.14 if layered else 0.045
    bump.inputs["Distance"].default_value = 0.000025 if layered else 0.000008
    if layered:
        wave = nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = 2200
        wave.inputs["Distortion"].default_value = 0.3
        links.new(tex.outputs["Object"], wave.inputs["Vector"])
        links.new(wave.outputs["Color"], bump.inputs["Height"])
    else:
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])


<<<<<<< HEAD
def readable_pet():
    """Illustrative cool PET tint and broad highlights; transmission stays fully enabled."""
    mat = material(
        "Unmeasured clear PET wall", (0.82, 0.90, 0.94), 0.08, transmission=1, ior=1.575
    )
    surface_detail(mat, roughness_range=(0.06, 0.12))
    # An assumed absorption coefficient gives long paths through the thin wall
    # a readable edge while leaving the centre transmissive, rather than opaque.
    absorption = mat.node_tree.nodes.new("ShaderNodeVolumeAbsorption")
    absorption.inputs["Color"].default_value = (0.45, 0.70, 0.78, 1)
    absorption.inputs["Density"].default_value = 250
    mat.node_tree.links.new(
        absorption.outputs["Volume"], mat.node_tree.nodes.get("Material Output").inputs["Volume"]
    )
    return mat


=======
>>>>>>> origin/checkpoint/video-worktree-20261106
def asphalt(cache):
    mat = material("Photographed asphalt / Poly Haven CC0", (0.1, 0.1, 0.1), 0.9)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    uv = nodes.new("ShaderNodeTexCoord")
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[3].default_value = 1 / 3
    links.new(uv.outputs["Object"], scale.inputs[0])
    images = {}
    for key, file in [
        ("color", "ground-diff.jpg"),
        ("normal", "ground-normal.jpg"),
        ("rough", "ground-rough.jpg"),
    ]:
        node = nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(Path(cache) / file))
        if key != "color":
            node.image.colorspace_settings.name = "Non-Color"
        links.new(scale.outputs["Vector"], node.inputs["Vector"])
        images[key] = node
    links.new(images["color"].outputs["Color"], shader.inputs["Base Color"])
    links.new(images["rough"].outputs["Color"], shader.inputs["Roughness"])
    normal = nodes.new("ShaderNodeNormalMap")
    normal.inputs["Strength"].default_value = 0.6
    links.new(images["normal"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return mat
