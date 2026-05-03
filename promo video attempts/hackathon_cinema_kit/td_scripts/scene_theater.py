"""
Scene 5: "The Theater"
Darkened cinema. Audience silhouettes. Massive curved screen showing epic trailer.
Camera pushes through the screen.
"""

scene = op('/project1/scene_theater')

# ---- THEATER ENVIRONMENT ----
# Curved screen
screen = scene.create('gridSOP', 'cinema_screen')
screen.par.rows = 24
screen.par.cols = 48
screen.par.size1 = 16
screen.par.size2 = 9

# Bend the screen
bend = scene.create('bendSOP', 'screen_bend')
bend.par.dir = 'X Axis'
bend.par.amount = 0.15
bend.inputConnectors[0].connect(screen)

# Screen content (movie playing on it)
screen_content = scene.create('moviefileinTOP', 'trailer_content')
screen_content.par.file = "assets/trailer_comp.mp4"  # placeholder
screen_content.par.resolutionw = 1920
screen_content.par.resolutionh = 1080

# Convert TOP to SOP texture
top_to_sop = scene.create('soptoCHOP', 'screen_tex_coords')
# Actually we need a Material with the TOP
screen_mat = scene.create('pbrMAT', 'screen_mat')
screen_mat.par.basecolormap = screen_content.path
screen_mat.par.emitr = 0.8
screen_mat.par.emitg = 0.8
screen_mat.par.emitb = 0.9
screen_mat.par.metallic = 0.0
screen_mat.par.roughness = 0.8

screen_geo = scene.create('geoCOMP', 'screen_geo')
screen_geo.par.material = screen_mat.path
screen_geo.inputConnectors[0].connect(bend)

# ---- AUDIENCE SILHOUETTES ----
# Simple instanced human shapes (capsules)
body = scene.create('capsuleSOP', 'audience_body')
body.par.rad = 0.15
body.par.height = 0.5
body.par.rows = 4
body.par.cols = 8

head = scene.create('sphereSOP', 'audience_head')
head.par.rad = 0.1
head.par.rows = 4
head.par.cols = 4

# Merge body+head
merge = scene.create('mergeSOP', 'person_merge')
merge.inputConnectors[0].connect(body)
merge.inputConnectors[1].connect(head)

# Instance audience
audience = scene.create('geoCOMP', 'audience')
audience.par.instancing = 1
audience.par.instancetx = 'tx'
audience.par.instancety = 'ty'
audience.par.instancetz = 'tz'

audience_mat = scene.create('phongMAT', 'silhouette_mat')
audience_mat.par.diffuser = 0.02
audience_mat.par.diffuseg = 0.02
audience_mat.par.diffuseb = 0.03
audience_mat.par.ambientr = 0.01
audience_mat.par.ambientg = 0.01
audience_mat.par.ambientb = 0.02

audience.par.material = audience_mat.path
audience.inputConnectors[0].connect(merge)

# ---- CAMERA PUSH ----
cam = scene.create('cameraCOMP', 'theater_cam')
cam.par.tz = -12
cam.par.ty = 1.2
cam.par.rx = 5
cam.par.fov = 45

# Animate push through screen
# z: -12 → 2 over the scene duration

# ---- LIGHTING ----
# Screen glow lights the room
screen_light = scene.create('lightCOMP', 'screen_glow')
screen_light.par.lighttype = 'Point'
screen_light.par.tx = 0
screen_light.par.ty = 2
screen_light.par.tz = 2
screen_light.par.colorr = 0.7
screen_light.par.colorg = 0.7
screen_light.par.colorb = 0.9
screen_light.par.intensity = 0.8
screen_light.par.attenuation = 'Distance and Angle'

# Subtle rim light
rim = scene.create('lightCOMP', 'rim_light')
rim.par.lighttype = 'Spot'
rim.par.tx = 8
rim.par.ty = 4
rim.par.tz = -8
rim.par.colorr = 0.1
rim.par.colorg = 0.05
rim.par.colorb = 0.2
rim.par.intensity = 0.5

# ---- RENDER ----
render = op('/project1/scene_theater/render_out')
render.inputConnectors[0].connect(screen_geo)
render.inputConnectors[1].connect(audience)
render.inputConnectors[2].connect(cam)
# Additional inputs for lights
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.005
render.par.clearcolorg = 0.005
render.par.clearcolorb = 0.01

# Post: vignette + film grain
vignette = scene.create('rampTOP', 'vignette')
vignette.par.type = 'radial'
vignette.par.resolutionw = 1920
vignette.par.resolutionh = 1080
vignette.par.color1r = 0
vignette.par.color1g = 0
vignette.par.color1b = 0
vignette.par.color2r = 1
vignette.par.color2g = 1
vignette.par.color2b = 1

vig_mult = scene.create('mathTOP', 'vig_mult')
vig_mult.inputConnectors[0].connect(render)
vig_mult.inputConnectors[1].connect(vignette)
vig_mult.par.multiply = 1

null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(vig_mult)

print("[Scene 5: The Theater] Built.")
