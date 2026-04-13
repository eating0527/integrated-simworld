import bpy
zip_path = r"C:\Users\user\Downloads\blosm_2.7.25.zip"
print('ZIP_EXISTS', __import__('os').path.exists(zip_path))
res1 = bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
print('INSTALL_RESULT', res1)
try:
    res2 = bpy.ops.preferences.addon_enable(module='blosm')
    print('ENABLE_RESULT', res2)
except Exception as e:
    print('ENABLE_ERROR', repr(e))
print('ENABLED_NOW', 'blosm' in bpy.context.preferences.addons.keys())
try:
    res3 = bpy.ops.wm.save_userpref()
    print('SAVE_PREF_RESULT', res3)
except Exception as e:
    print('SAVE_PREF_ERROR', repr(e))
