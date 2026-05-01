"""
Scene 4: "Social Velocity"
Hyperspace tunnel of social media UI frames. Fast, chaotic, colorful.
"""

scene = op('/project1/scene_social')

# ---- TUNNEL GEOMETRY ----
tunnel = scene.create('tubeSOP', 'tunnel_geo')
tunnel.par.rad1 = 4
tunnel.par.rad2 = 4
tunnel.par.height = 40
tunnel.par.rows = 2
tunnel.par.cols = 32

tunnel_xform = scene.create('transformSOP', 'tunnel_xform')
tunnel_xform.par.ry = 90
tunnel_xform.inputConnectors[0].connect(tunnel)

# Texture the tunnel with scrolling grid
grid_tex = scene.create('rampTOP', 'tunnel_grid')
grid_tex.par.type = 'horizontal'
grid_tex.par.resolutionw = 2048
grid_tex.par.resolutionh = 2048

noise_tex = scene.create('noiseTOP', 'grid_noise')
noise_tex.par.resolutionw = 2048
noise_tex.par.resolutionh = 2048
noise_tex.par.type = 'Perlin'
noise_tex.par.period = 0.02

scroll = scene.create('transformTOP', 'scroll_grid')
scroll.inputConnectors[0].connect(grid_tex)
scroll.par.ty = -0.05  # scroll speed

comp_tex = scene.create('compositeTOP', 'tunnel_tex')
comp_tex.inputConnectors[0].connect(scroll)
comp_tex.inputConnectors[1].connect(noise_tex)
comp_tex.par.operation = 'Add'

tunnel_mat = scene.create('phongMAT', 'tunnel_mat')
tunnel_mat.par.diffusemap = comp_tex.path
tunnel_mat.par.emitr = 0.1
tunnel_mat.par.emitg = 0.0
tunnel_mat.par.emitb = 0.2

tunnel_geo_comp = scene.create('geoCOMP', 'tunnel')
tunnel_geo_comp.par.material = tunnel_mat.path
tunnel_geo_comp.inputConnectors[0].connect(tunnel_xform)

# ---- FLYING FRAMES ----
frame_sop = scene.create('rectangleSOP', 'frame_geo')
frame_sop.par.size1 = 0.9
frame_sop.par.size2 = 1.6

# Instance frames flying toward camera
frame_instancer = scene.create('geoCOMP', 'flying_frames')
frame_instancer.par.instancing = 1
frame_instancer.par.instancetx = 'tx'
frame_instancer.par.instancety = 'ty'
frame_instancer.par.instancetz = 'tz'
frame_instancer.par.instancerx = 'rx'
frame_instancer.par.instancery = 'ry'
frame_instancer.par.instancerz = 'rz'

frame_mat = scene.create('pbrMAT', 'frame_mat')
frame_mat.par.basecolorr = 1
frame_mat.par.basecolorg = 1
frame_mat.par.basecolorb = 1
frame_mat.par.metallic = 0.1
frame_mat.par.roughness = 0.4

frame_instancer.par.material = frame_mat.path
frame_instancer.inputConnectors[0].connect(frame_sop)

# ---- CAMERA ----
cam = scene.create('cameraCOMP', 'velocity_cam')
cam.par.tz = -15
cam.par.fov = 80

# Camera shake
noise_shake = scene.create('noiseCHOP', 'cam_shake')
noise_shake.par.type = 'Perlin'
noise_shake.par.period = 0.1
noise_shake.par.speed = 8

# ---- LIGHTING ----
light1 = scene.create('lightCOMP', 'neon_pink')
light1.par.lighttype = 'Point'
light1.par.tx = -3
light1.par.ty = 2
light1.par.tz = -5
light1.par.colorr = 1.0
light1.par.colorg = 0.0
light1.par.colorb = 0.43
light1.par.intensity = 2.0

light2 = scene.create('lightCOMP', 'neon_cyan')
light2.par.lighttype = 'Point'
light2.par.tx = 3
light2.par.ty = -2
light2.par.tz = -5
light2.par.colorr = 0.0
light2.par.colorg = 0.94
light2.par.colorb = 1.0
light2.par.intensity = 2.0

# ---- RENDER ----
render = op('/project1/scene_social/render_out')
render.inputConnectors[0].connect(tunnel_geo_comp)
render.inputConnectors[1].connect(cam)
render.inputConnectors[2].connect(light1)
# TD only has 3 light inputs on renderTOP usually, use light1 for both or merge
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.05
render.par.clearcolorg = 0.0
render.par.clearcolorb = 0.08

# Post: chromatic aberration + motion blur
blur = scene.create('blurTOP', 'motion_blur')
blur.inputConnectors[0].connect(render)
blur.par.size = 0.015
blur.par.mask = 1

rgb = scene.create('rgbkeyTOP', 'chromatic')
rgb.inputConnectors[0].connect(blur)
rgb.par.rgbscale = 1.02

null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(rgb)

print("[Scene 4: Social Velocity] Built.")
