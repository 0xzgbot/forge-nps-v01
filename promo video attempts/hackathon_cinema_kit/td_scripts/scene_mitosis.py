"""
Scene 2: "Mitosis"
One image becomes many. Grid expansion with morphing textures.
"""

scene = op('/project1/scene_mitosis')

# ---- SOURCE IMAGE ----
source = scene.create('moviefileinTOP', 'source_image')
source.par.file = "assets/spark_01.png"  # placeholder
source.par.resolutionw = 512
source.par.resolutionh = 512

# Replicate into grid
replicator = scene.create('replicatorCOMP', 'image_grid')
replicator.par.master = source.path
replicator.par.orientation = 'row'
replicator.par.cols = 8
replicator.par.rows = 5
replicator.par.spacingx = 1.2
replicator.par.spacingy = 1.2

# Camera pull-back animation
cam = scene.create('cameraCOMP', 'pullback_cam')
cam.par.tz = 20
cam.par.ty = 2
cam.par.fov = 50

# Animate camera
anim = scene.create('animationCOMP', 'cam_anim')
anim.par.length = 300  # 10s at 30fps
anim.par.keys = '[[0,20],[300,8]]'  # pull from z=20 to z=8

light = scene.create('lightCOMP', 'fill_light')
light.par.lighttype = 'Directional'
light.par.tx = -2
light.par.ty = 5
light.par.tz = 4

# Render
render = op('/project1/scene_mitosis/render_out')
render.inputConnectors[0].connect(replicator)
render.inputConnectors[1].connect(cam)
render.inputConnectors[2].connect(light)
render.par.resolutionw = 1920
render.par.resolutionh = 1080
render.par.clearcolorr = 0.01
render.par.clearcolorg = 0.01
render.par.clearcolorb = 0.02

# Post: slight glow
blur = scene.create('blurTOP', 'grid_glow')
blur.inputConnectors[0].connect(render)
blur.par.size = 0.008

comp = scene.create('compositeTOP', 'glow_comp')
comp.inputConnectors[0].connect(render)
comp.inputConnectors[1].connect(blur)
comp.par.operation = 'Add'

null_out = scene.create('nullTOP', 'scene_out')
null_out.inputConnectors[0].connect(comp)

print("[Scene 2: Mitosis] Built.")
