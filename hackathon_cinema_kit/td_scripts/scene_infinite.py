"""
Scene 6: "Infinite Studio"
Recursive monitor hall. Forge logo at center of neural network.
Elegant, clean, impactful lockup.
"""

scene = op('/project1/scene_infinite')

# ---- LOGO GEOMETRY ----
logo_text = scene.create('textSOP', 'logo_sop')
logo_text.par.text = 'FORGE'
logo_text.par.fontsizex = 1.5
logo_text.par.align = 'Center'
logo_text.par.borders = 1

# Extrude for 3D depth
extrude = scene.create('extrudeSOP', 'logo_3d')
extrude.par.depth = 0.2
extrude.inputConnectors[0].connect(logo_text)

logo_mat = scene.create('pbrMAT', 'logo_mat')
logo_mat.par.basecolorr = 0.48
logo_mat.par.basecolorg = 0.23
logo_mat.par.basecolorb = 0.93  # Forge purple
logo_mat.par.metallic = 0.9
logo_mat.par.roughness = 0.1
logo_mat.par.emitr = 0.1
logo_mat.par.emitg = 0.05
logo_mat.par.emitb = 0.3

logo_geo = scene.create('geoCOMP', 'logo_geo')
logo_geo.par.material = logo_mat.path
logo_geo.inputConnectors[0].connect(extrude)

# ---- NEURAL NETWORK RINGS ----
ring = scene.create('torusSOP', 'network_ring')
ring.par.rad1 = 3.0
ring.par.rad2 = 0.02
ring.par.rows = 2
ring.par.cols = 64

# Multiple rings at different angles
for i in range(3):
    angle = i * 60
    rxform = scene.create('transformSOP', f'ring_{i}_xform')
    rxform.par.rx = angle
    rxform.par.ry = angle * 0.7
    rxform.par.rz = angle * 0.3
    rxform.par.sx = 1.0 + i * 0.4
    rxform.par.sy = 1.0 + i * 0.4
    rxform.par.sz = 1.0 + i * 0.4
    rxform.inputConnectors[0].connect(ring)
    
    rmat = scene.create('basicMAT', f'ring_{i}_mat')
    rmat.par.colorr = 0.3 + i * 0.2
    rmat.par.colorg = 0.1
    rmat.par.colorb = 0.5 + i * 0.15
    rmat.par.alpha = 0.6 - i * 0.15
    rmat.par.wireframe = 1
    
    rgeo = scene.create('geoCOMP', f'ring_{i}_geo')
    rgeo.par.material = rmat.path
    rgeo.inputConnectors[0].connect(rxform)

# ---- FLOATING MONITORS (Instanced) ----
monitor = scene.create('rectangleSOP', 'monitor_geo')
monitor.par.size1 = 0.8
monitor.par.size2 = 0.5

monitors = scene.create('geoCOMP', 'monitor_wall')
monitors.par.instancing = 1
monitors.par.instancetx = 'tx'
monitors.par.instancety = 'ty'
monitors.par.instancetz = 'tz'
monitors.par.instancerx = 'rx'
monitors.par.instancery = 'ry'

mon_mat = scene.create('pbrMAT', 'monitor_mat')
mon_mat.par.basecolorr = 0.1
mon_mat.par.basecolorg = 0.1
mon_mat.par.basecolorb = 0.15
mon_mat.par.metallic = 0.8
mon_mat.par.roughness = 0.2
monitors.par.material = mon_mat.path
monitors.inputConnectors[0].connect(monitor)

# ---- TAGLINE ----
tagline = scene.create('textTOP', 'tagline')
tagline.par.text = 'From Prompt to Premiere'
tagline.par.fontsizex = 0.025
tagline.par.fontsizey = 0.04
tagline.par.alignx = 0.5
tagline.par.aligny = 0.5
tagline.par.resolutionw = 1920
tagline.par.resolutionh = 200
tagline.par.colorr = 0.8
tagline.par.colorg = 0.8
tagline.par.colorb = 0.85

# ---- CAMERA ----
cam = scene.create('cameraCOMP', 'infinite_cam')
cam.par.tz = 10
cam.par.ty = 1
cam.par.rx = -5

# Slow rotate
# animate ry over the scene

# ---- LIGHTING ----
center_light = scene.create('lightCOMP', 'center_glow')
center_light.par.lighttype = 'Point'
center_light.par.tx = 0
center_light.par.ty = 0
center_light.par.tz = 1
center_light.par.colorr = 0.48
center_light.par.colorg = 0.23
center_light.par.colorb = 0.93
center_light.par.intensity = 3.0

fill = scene.create('lightCOMP', 'infinite_fill')
fill.par.lighttype = 'Directional'
fill.par.tx = -2
fill.par.ty = 3
fill.par.tz = 2
fill.par.intensity = 0.3

# ---- RENDER ----
render = op('/project1/scene_infinite/render_out')
render.inputConnectors[0].connect(logo_geo)
render.inputConnectors[1].connect(cam)
render.inputConnectors[2].connect(center_light)
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.01
render.par.clearcolorg = 0.01
render.par.clearcolorb = 0.015

# Post: subtle glow + stars
starfield = scene.create('noiseTOP', 'stars')
starfield.par.resolutionw = 1920
starfield.par.resolutionh = 1080
starfield.par.type = 'Sparse'
starfield.par.period = 0.003
starfield.par.amplitude = 2.0

level = scene.create('levelTOP', 'star_levels')
level.inputConnectors[0].connect(starfield)
level.par.blacklevel = 0.8
level.par.whitelevel = 1.0

comp = scene.create('compositeTOP', 'stars_comp')
comp.inputConnectors[0].connect(render)
comp.inputConnectors[1].connect(level)
comp.par.operation = 'Add'

# Overlay tagline
over = scene.create('overTOP', 'tagline_over')
over.inputConnectors[0].connect(comp)
over.inputConnectors[1].connect(tagline)
over.par.alignx = 0.5
over.par.aligny = 0.85

null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(over)

print("[Scene 6: Infinite Studio] Built.")
