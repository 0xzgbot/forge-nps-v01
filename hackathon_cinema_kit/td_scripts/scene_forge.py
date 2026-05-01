"""
Scene 3: "The Forge"
Abstract pipeline visualization. Shots flow as orbs through agent nodes.
"""

scene = op('/project1/scene_forge')

# ---- PIPELINE NODES (Static Geometry) ----
node_names = ["Prompt", "Image\nAnalyst", "Duration\nPlanner", "Prompt\nEngineer", "ComfyUI", "Render"]
node_colors = [
    (1.0, 0.7, 0.0),   # Gold - Prompt
    (0.3, 1.0, 0.8),   # Cyan - Analyst
    (0.8, 1.0, 0.3),   # Lime - Planner
    (0.8, 0.5, 1.0),   # Purple - Engineer
    (0.0, 0.8, 1.0),   # Blue - ComfyUI
    (1.0, 0.9, 1.0),   # White - Render
]

# Create node spheres
base_geo = scene.create('sphereSOP', 'node_sphere')
base_geo.par.rad = 0.3
base_geo.par.rows = 16
base_geo.par.cols = 16

for i, (name, color) in enumerate(zip(node_names, node_colors)):
    tx = (i - 2.5) * 2.5
    transform = scene.create('transformSOP', f'node_{i}_xform')
    transform.par.tx = tx
    transform.par.ty = 0
    transform.par.tz = 0
    transform.inputConnectors[0].connect(base_geo)
    
    mat = scene.create('phongMAT', f'node_{i}_mat')
    mat.par.diffuser = color[0]
    mat.par.diffuseg = color[1]
    mat.par.diffuseb = color[2]
    mat.par.ambientr = color[0] * 0.3
    mat.par.ambientg = color[1] * 0.3
    mat.par.ambientb = color[2] * 0.3
    
    geo = scene.create('geoCOMP', f'node_{i}_geo')
    geo.par.material = mat.path
    geo.inputConnectors[0].connect(transform)
    
    # Label
    label = scene.create('textTOP', f'node_{i}_label')
    label.par.text = name
    label.par.fontsizex = 0.012
    label.par.fontsizey = 0.02
    label.par.resolutionw = 256
    label.par.resolutionh = 128
    label.par.colorr = color[0]
    label.par.colorg = color[1]
    label.par.colorb = color[2]

# ---- FLOWING ORBS ----
orb_geo = scene.create('sphereSOP', 'orb')
orb_geo.par.rad = 0.12
orb_geo.par.rows = 8
orb_geo.par.cols = 8

# CHOP network for orb animation
anim_chop = scene.create('choptoSOP', 'orb_anim')
# We'll use a Trail CHOP to animate positions
trail = scene.create('trailCHOP', 'orb_trail')
trail.par.length = 120

# Instance many orbs along the pipeline
instancer = scene.create('geoCOMP', 'orb_instancer')
instancer.par.instancing = 1
instancer.par.instancetx = 'tx'
instancer.par.instancety = 'ty'
instancer.par.instancetz = 'tz'
instancer.par.instancecolorr = 'cr'
instancer.par.instancecolorg = 'cg'
instancer.par.instancecolorb = 'cb'

# GLSL MAT for orb glow
orb_mat = scene.create('phongMAT', 'orb_mat')
orb_mat.par.diffuser = 1.0
orb_mat.par.diffuseg = 1.0
orb_mat.par.diffuseb = 1.0
orb_mat.par.emitr = 0.8
orb_mat.par.emitg = 0.8
orb_mat.par.emitb = 1.0
instancer.par.material = orb_mat.path
instancer.inputConnectors[0].connect(orb_geo)

# ---- CONNECTION LINES ----
line_sop = scene.create('lineSOP', 'pipeline_line')
line_sop.par.pts = [(-6.25,0,0), (6.25,0,0)]
line_mat = scene.create('basicMAT', 'line_mat')
line_mat.par.wireframe = 1
line_mat.par.colorr = 0.2
line_mat.par.colorg = 0.2
line_mat.par.colorb = 0.3
line_mat.par.alpha = 0.5

line_geo = scene.create('geoCOMP', 'pipeline_line_geo')
line_geo.par.material = line_mat.path
line_geo.inputConnectors[0].connect(line_sop)

# ---- RENDER ----
cam = scene.create('cameraCOMP', 'forge_cam')
cam.par.tz = 8
cam.par.ty = 2
cam.par.rx = -15

light = scene.create('lightCOMP', 'forge_light')
light.par.lighttype = 'Point'
light.par.tx = 0
light.par.ty = 4
light.par.tz = 3
light.par.intensity = 1.5

render = op('/project1/scene_forge/render_out')
render.inputConnectors[0].connect(instancer)
render.inputConnectors[1].connect(cam)
render.inputConnectors[2].connect(light)
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.01
render.par.clearcolorg = 0.01
render.par.clearcolorb = 0.02

# Post: scanlines + glow
scan = scene.create('rampTOP', 'scanlines')
scan.par.type = 'vertical'
scan.par.resolutionw = 1920
scan.par.resolutionh = 1080

mult = scene.create('mathTOP', 'scan_mult')
mult.inputConnectors[0].connect(render)
mult.inputConnectors[1].connect(scan)
mult.par.multiply = 1

null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(mult)

print("[Scene 3: The Forge] Built.")
