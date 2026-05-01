"""
Scene 1: "The Spark"
Text prompt condenses from particle noise, then ignites to reveal first image.
Run after build_master_network.py
"""

scene = op('/project1/scene_spark')

# ---- TEXT GENERATION ----
text_top = scene.create('textTOP', 'prompt_text')
text_top.par.text = '"A trail runner crests a granite ridge, golden hour light, dust particles in air, cinematic wide shot"'
text_top.par.fontsizex = 0.015
text_top.par.fontsizey = 0.025
text_top.par.alignx = 0.5
text_top.par.aligny = 0.5
text_top.par.colorr = 0.9
text_top.par.colorg = 0.9
text_top.par.colorb = 0.9
text_top.par.resolutionw = 1920
text_top.par.resolutionh = 1080

# ---- NOISE PARTICLES ----
noise = scene.create('noiseCHOP', 'text_noise')
noise.par.type = 'Sparse'
noise.par.period = 0.05
noise.par.speed = 0.8

# Convert noise to points
sop = scene.create('soptoCHOP', 'noise_to_sop')
# Create a grid of points that will be our particle field
grid = scene.create('gridSOP', 'particle_grid')
grid.par.rows = 80
grid.par.cols = 120
grid.par.size1 = 16
grid.par.size2 = 9

# Add noise displacement
noise_sop = scene.create('noiseSOP', 'displace')
noise_sop.par.rx = 0.3
noise_sop.par.ry = 0.3
noise_sop.par.rz = 0.1
noise_sop.inputConnectors[0].connect(grid)

# Particle system
particles = scene.create('particleSOP', 'dust_particles')
particles.inputConnectors[0].connect(noise_sop)
particles.par.life = 3.0
particles.par.lifevar = 1.5
particles.par.speed = 0.2
particles.par.speedvar = 0.1

# Render particles
mat = scene.create('pointspriteMAT', 'dust_mat')
mat.par.colorr = 0.6
mat.par.colorg = 0.4
mat.par.colorb = 1.0
mat.par.pointcolorr = 0.8
mat.par.pointcolorg = 0.6
mat.par.pointcolorb = 1.0
mat.par.size = 0.02

cam = scene.create('cameraCOMP', 'scene_cam')
cam.par.tz = 8
cam.par.ty = 0.5

light = scene.create('lightCOMP', 'key_light')
light.par.lighttype = 'Point'
light.par.tx = 3
light.par.ty = 4
light.par.tz = 3

geo = scene.create('geoCOMP', 'particle_geo')
geo.par.material = mat.path
geo.inputConnectors[0].connect(particles)

render = op('/project1/scene_spark/render_out')
render.inputConnectors[0].connect(geo)
render.inputConnectors[1].connect(cam)
render.inputConnectors[2].connect(light)
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.02
render.par.clearcolorg = 0.02
render.par.clearcolorb = 0.02

# ---- COMPOSITE: Text over particles ----
over = scene.create('overTOP', 'text_over_particles')
over.inputConnectors[0].connect(render)
over.inputConnectors[1].connect(text_top)

# ---- FEEDBACK BURN EFFECT ----
feedback = scene.create('feedbackTOP', 'burn_feedback')
feedback.inputConnectors[0].connect(over)
feedback.par.resolutionw = 1920
feedback.par.resolutionh = 1080

xform = scene.create('transformTOP', 'feedback_transform')
xform.inputConnectors[0].connect(feedback)
xform.par.sx = 1.003
xform.par.sy = 1.003
xform.par.opacity = 0.96

comp = scene.create('compositeTOP', 'burn_comp')
comp.inputConnectors[0].connect(over)
comp.inputConnectors[1].connect(xform)
comp.par.operation = 'Over'

# Feedback loop
feedback.inputConnectors[0].connect(comp)

# Final scene output
null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(comp)
null_out.par.resolutionw = 1920
null_out.par.resolutionh = 1080

print("[Scene 1: Spark] Built. Connect /project1/scene_spark/scene_out to crossfader.")
