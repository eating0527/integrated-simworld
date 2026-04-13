import bpy
mods = bpy.context.preferences.addons.keys()
print('HAS_BLOSM=' + str('blosm' in mods))
print('ADDONS=' + ','.join(sorted(list(mods))[:20]))
