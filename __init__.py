bl_info = {
    "name": "Easy Library",
    "author": "Jopex Creatives",
    "version": (1, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Easy Library",
    "description": "Dynamic asset library for Blender with thumbnail previews",
    "category": "Object",
    "doc_url": "https://github.com/jopexcreatives",
}

import bpy
import os
import shutil
import bpy.utils.previews
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, EnumProperty, PointerProperty, IntProperty
from bpy.types import Operator, Panel, PropertyGroup

# Path to assets folder (relative to this script)
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# -----------------------------------------------------------------
#  Preview collection
# -----------------------------------------------------------------
preview_collections = {}

def get_pcoll(category_path):
    """Get or create preview collection for a category"""
    if category_path not in preview_collections:
        preview_collections[category_path] = bpy.utils.previews.new()
    return preview_collections[category_path]

def get_icon_id(filepath, display_name, category_path):
    """Return icon_id for an asset, loading thumbnail if available.

    Only ever loads existing image data - never renders anything - because
    this is called from inside Panel.draw(), where render operators are
    unsafe and will silently fail.
    """
    pcoll = get_pcoll(category_path)

    if filepath in pcoll:
        return pcoll[filepath].icon_id

    # 1) External thumbnail image next to the asset, if one exists
    for ext in ['.png', '.jpg', '.jpeg']:
        thumb_path = os.path.join(category_path, display_name + ext)
        if os.path.exists(thumb_path):
            try:
                pcoll.load(filepath, thumb_path, 'IMAGE')
                return pcoll[filepath].icon_id
            except Exception:
                pass

    # 2) Fallback: embedded preview stored inside the .blend file itself
    if filepath.lower().endswith('.blend'):
        try:
            pcoll.load(filepath, filepath, 'BLEND')
            return pcoll[filepath].icon_id
        except Exception:
            pass

    return 0

def clear_previews():
    """Clear all preview collections"""
    global preview_collections
    for pcoll in preview_collections.values():
        try:
            bpy.utils.previews.remove(pcoll)
        except Exception:
            pass
    preview_collections.clear()

custom_icons = None

def register_custom_icons():
    global custom_icons
    custom_icons = bpy.utils.previews.new()
    logo_path = os.path.join(ASSETS_DIR, "..", "jopexlogo.png")
    if os.path.exists(logo_path):
        custom_icons.load("jopex_logo", logo_path, 'IMAGE')

def unregister_custom_icons():
    global custom_icons
    if custom_icons:
        bpy.utils.previews.remove(custom_icons)
        custom_icons = None

# -----------------------------------------------------------------
#  Properties
# -----------------------------------------------------------------
class EasyLibraryProps(PropertyGroup):
    search_query: StringProperty(name="", description="Search assets", default="")
    expanded_folders: StringProperty(default="")
    grid_columns: IntProperty(
        name="Columns",
        description="Number of thumbnails per row (1-4)",
        default=2,
        min=1,
        max=4,
    )

# -----------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------
def get_existing_folders(self, context):
    items = []
    if os.path.exists(ASSETS_DIR):
        for d in sorted(os.listdir(ASSETS_DIR)):
            if os.path.isdir(os.path.join(ASSETS_DIR, d)):
                items.append((d, d, ""))
    return items or [('NONE', "No folders found", "")]

def get_folder_items_with_new(self, context):
    items = get_existing_folders(self, context)
    if items[0][0] == 'NONE':
        items = []
    items.append(('__NEW__', "+ Create New Folder", ""))
    return items

def get_all_assets(self, context):
    items = []
    if os.path.exists(ASSETS_DIR):
        for d in sorted(os.listdir(ASSETS_DIR)):
            cat_path = os.path.join(ASSETS_DIR, d)
            if os.path.isdir(cat_path):
                for f in sorted(os.listdir(cat_path)):
                    if f.lower().endswith(('.blend', '.fbx', '.exr', '.hdr', '.obj', '.glb', '.gltf')):
                        items.append((os.path.join(d, f), os.path.join(d, f), ""))
    return items or [('NONE', "No assets found", "")]

# -----------------------------------------------------------------
#  Operators - Management
# -----------------------------------------------------------------
class EASYLIB_OT_open_readme(Operator):
    bl_idname = "easylib.open_readme"
    bl_label = "Open Documentation"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        path = os.path.join(os.path.dirname(__file__), "README.md")
        if os.path.exists(path):
            bpy.ops.wm.url_open(url="file:///" + path.replace(os.sep, '/'))
        else:
            self.report({'WARNING'}, "README.md not found!")
        return {'FINISHED'}

class EASYLIB_OT_confirm_action(Operator):
    bl_idname = "easylib.confirm_action"
    bl_label = "Confirm Delete"
    bl_options = {'REGISTER', 'INTERNAL'}

    action: StringProperty()
    target_path: StringProperty()
    display_name: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="Permanently delete:", icon='ERROR')
        col.label(text=self.display_name)
        col.label(text="This cannot be undone!")

    def execute(self, context):
        if self.action == "DELETE_FOLDER":
            if os.path.exists(self.target_path):
                shutil.rmtree(self.target_path)
                clear_previews()
                self.report({'INFO'}, f"Deleted folder: {self.display_name}")
        elif self.action == "DELETE_ASSET":
            if os.path.exists(self.target_path):
                os.remove(self.target_path)
                base = os.path.splitext(self.target_path)[0]
                for t in ['.png', '.jpg', '.jpeg']:
                    tp = base + t
                    if os.path.exists(tp):
                        os.remove(tp)
                clear_previews()
                self.report({'INFO'}, f"Deleted: {self.display_name}")
        return {'FINISHED'}

class EASYLIB_OT_add_folder(Operator):
    bl_idname = "easylib.add_folder"
    bl_label = "Create Folder"
    bl_options = {'REGISTER', 'UNDO'}

    folder_name: StringProperty(name="Folder Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.folder_name:
            self.report({'ERROR'}, "Folder name cannot be empty")
            return {'CANCELLED'}
        new_path = os.path.join(ASSETS_DIR, self.folder_name)
        if not os.path.exists(new_path):
            os.makedirs(new_path)
            self.report({'INFO'}, f"Created: {self.folder_name}")
        else:
            self.report({'WARNING'}, "Folder already exists")
        return {'FINISHED'}

class EASYLIB_OT_remove_folder(Operator):
    bl_idname = "easylib.remove_folder"
    bl_label = "Delete Folder"
    bl_options = {'REGISTER', 'UNDO'}

    target_folder: EnumProperty(name="Folder to Delete", items=get_existing_folders)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.target_folder == 'NONE':
            return {'CANCELLED'}
        tp = os.path.join(ASSETS_DIR, self.target_folder)
        bpy.ops.easylib.confirm_action('INVOKE_DEFAULT',
                                       action="DELETE_FOLDER",
                                       target_path=tp,
                                       display_name=self.target_folder)
        return {'FINISHED'}

class EASYLIB_OT_rename_folder(Operator):
    bl_idname = "easylib.rename_folder"
    bl_label = "Rename Folder"
    bl_options = {'REGISTER', 'UNDO'}

    target_folder: EnumProperty(name="Folder", items=get_existing_folders)
    new_name: StringProperty(name="New Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.target_folder == 'NONE' or not self.new_name:
            return {'CANCELLED'}
        src = os.path.join(ASSETS_DIR, self.target_folder)
        dst = os.path.join(ASSETS_DIR, self.new_name)
        if not os.path.exists(dst):
            os.rename(src, dst)
            clear_previews()
            self.report({'INFO'}, "Folder renamed")
        else:
            self.report({'WARNING'}, "Name already exists")
        return {'FINISHED'}

class EASYLIB_OT_add_asset_file(Operator, ImportHelper):
    bl_idname = "easylib.add_asset_file"
    bl_label = "Add Asset"
    bl_description = "Copy a file into the library"

    filter_glob: StringProperty(
        default="*.blend;*.fbx;*.obj;*.glb;*.gltf;*.exr;*.hdr",
        options={'HIDDEN'})
    target_folder: EnumProperty(name="Target Folder", items=get_folder_items_with_new)
    new_folder_name: StringProperty(name="New Folder Name")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_folder")
        if self.target_folder == '__NEW__':
            layout.prop(self, "new_folder_name")

    def execute(self, context):
        folder_name = self.target_folder
        if folder_name == '__NEW__':
            folder_name = self.new_folder_name
            if not folder_name:
                self.report({'ERROR'}, "New folder name cannot be empty")
                return {'CANCELLED'}
        os.makedirs(ASSETS_DIR, exist_ok=True)
        target_path = os.path.join(ASSETS_DIR, folder_name)
        os.makedirs(target_path, exist_ok=True)
        dest = os.path.join(target_path, os.path.basename(self.filepath))
        try:
            shutil.copy2(self.filepath, dest)
            clear_previews()
            self.report({'INFO'}, f"Added: {os.path.basename(self.filepath)}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed: {e}")
            return {'CANCELLED'}

class EASYLIB_OT_remove_asset_dialog(Operator):
    bl_idname = "easylib.remove_asset_dialog"
    bl_label = "Remove Asset"
    bl_options = {'REGISTER', 'UNDO'}

    target_asset: EnumProperty(name="Asset to Delete", items=get_all_assets)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.target_asset == 'NONE':
            return {'CANCELLED'}
        tp = os.path.join(ASSETS_DIR, self.target_asset)
        bpy.ops.easylib.confirm_action('INVOKE_DEFAULT',
                                       action="DELETE_ASSET",
                                       target_path=tp,
                                       display_name=self.target_asset)
        return {'FINISHED'}

class EASYLIB_OT_move_asset(Operator):
    bl_idname = "easylib.move_asset"
    bl_label = "Move Asset"
    bl_options = {'REGISTER', 'UNDO'}

    target_asset: EnumProperty(name="Asset to Move", items=get_all_assets)
    dest_folder: EnumProperty(name="Destination Folder", items=get_existing_folders)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.target_asset == 'NONE' or self.dest_folder == 'NONE':
            return {'CANCELLED'}
        src = os.path.join(ASSETS_DIR, self.target_asset)
        dst = os.path.join(ASSETS_DIR, self.dest_folder, os.path.basename(self.target_asset))
        if os.path.exists(src):
            shutil.move(src, dst)
            base = os.path.splitext(src)[0]
            dst_base = os.path.splitext(dst)[0]
            for t in ['.png', '.jpg', '.jpeg']:
                if os.path.exists(base + t):
                    shutil.move(base + t, dst_base + t)
            clear_previews()
            self.report({'INFO'}, f"Moved to {self.dest_folder}")
        return {'FINISHED'}

class EASYLIB_OT_rename_asset(Operator):
    bl_idname = "easylib.rename_asset"
    bl_label = "Rename Asset"
    bl_options = {'REGISTER', 'UNDO'}

    target_asset: EnumProperty(name="Asset", items=get_all_assets)
    new_name: StringProperty(name="New Name (no extension)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if self.target_asset == 'NONE' or not self.new_name:
            return {'CANCELLED'}
        src = os.path.join(ASSETS_DIR, self.target_asset)
        folder = os.path.dirname(src)
        ext = os.path.splitext(src)[1]
        dst = os.path.join(folder, self.new_name + ext)
        if not os.path.exists(dst):
            os.rename(src, dst)
            base = os.path.splitext(src)[0]
            for t in ['.png', '.jpg', '.jpeg']:
                if os.path.exists(base + t):
                    os.rename(base + t, os.path.join(folder, self.new_name + t))
            clear_previews()
            self.report({'INFO'}, "Asset renamed")
        else:
            self.report({'WARNING'}, "Name already exists")
        return {'FINISHED'}

class EASYLIB_OT_clear_search(Operator):
    bl_idname = "easylib.clear_search"
    bl_label = "Clear Search"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        context.scene.easylib_props.search_query = ""
        return {'FINISHED'}

class EASYLIB_OT_toggle_folder(Operator):
    bl_idname = "easylib.toggle_folder"
    bl_label = "Toggle Folder"
    bl_options = {'REGISTER', 'INTERNAL'}

    folder_name: StringProperty()

    def execute(self, context):
        props = context.scene.easylib_props
        expanded = set(props.expanded_folders.split("|")) if props.expanded_folders else set()
        if self.folder_name in expanded:
            expanded.remove(self.folder_name)
        else:
            expanded.add(self.folder_name)
        props.expanded_folders = "|".join(filter(None, expanded))
        return {'FINISHED'}

# -----------------------------------------------------------------
#  Operator - Add Asset to Scene
# -----------------------------------------------------------------
class EASYLIB_OT_add_asset(Operator):
    bl_idname = "easylib.add_asset"
    bl_label = "Add Asset to Scene"
    bl_options = {'REGISTER', 'UNDO'}

    file_path: StringProperty()
    display_name: StringProperty()

    def execute(self, context):
        if not os.path.exists(self.file_path):
            self.report({'ERROR'}, f"File not found: {self.file_path}")
            return {'CANCELLED'}
        bpy.ops.object.select_all(action='DESELECT')
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext in ['.exr', '.hdr']:
            return self._setup_hdri(context)
        elif ext == '.blend':
            return self._append_blend(context)
        elif ext == '.fbx':
            return self._import(context, 'import_scene.fbx')
        elif ext == '.obj':
            return self._import_obj(context)
        elif ext in ['.glb', '.gltf']:
            return self._import(context, 'import_scene.gltf')
        self.report({'ERROR'}, f"Unsupported: {ext}")
        return {'CANCELLED'}

    def _setup_hdri(self, context):
        try:
            world = context.scene.world or bpy.data.worlds.new("World")
            context.scene.world = world
            world.use_nodes = True
            nodes = world.node_tree.nodes
            links = world.node_tree.links
            nodes.clear()
            bg = nodes.new('ShaderNodeBackground')
            out = nodes.new('ShaderNodeOutputWorld')
            out.location = (200, 0)
            env = nodes.new('ShaderNodeTexEnvironment')
            env.location = (-300, 0)
            env.image = bpy.data.images.load(self.file_path)
            links.new(env.outputs['Color'], bg.inputs['Color'])
            links.new(bg.outputs['Background'], out.inputs['Surface'])
            self.report({'INFO'}, f"HDRI set: {self.display_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def _append_blend(self, context):
        try:
            imported = []
            with bpy.data.libraries.load(self.file_path, link=False) as (src, dst):
                dst.objects = src.objects
            for obj in dst.objects:
                if obj:
                    context.collection.objects.link(obj)
                    imported.append(obj)
                    obj.select_set(True)
            if imported:
                empty = bpy.data.objects.new(f"{self.display_name}_Empty", None)
                empty.empty_display_type = 'ARROWS'
                empty.empty_display_size = 2.0
                context.collection.objects.link(empty)
                for obj in imported:
                    obj.parent = empty
                empty.location = context.scene.cursor.location
                empty.select_set(True)
                context.view_layer.objects.active = empty
            self.report({'INFO'}, f"Added: {self.display_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def _import(self, context, op_string):
        try:
            module, op = op_string.split('.')
            getattr(getattr(bpy.ops, module), op)(filepath=self.file_path)
            self.report({'INFO'}, f"Imported: {self.display_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def _import_obj(self, context):
        try:
            if hasattr(bpy.ops.wm, 'obj_import'):
                bpy.ops.wm.obj_import(filepath=self.file_path)
            else:
                bpy.ops.import_scene.obj(filepath=self.file_path)
            self.report({'INFO'}, f"Imported: {self.display_name}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

# -----------------------------------------------------------------
#  Addon Preferences
# -----------------------------------------------------------------
class EasyLibraryPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        self.layout.operator(EASYLIB_OT_open_readme.bl_idname,
                             text="Documentation", icon='HELP')

# -----------------------------------------------------------------
#  Panel - Main UI with Custom Grid
# -----------------------------------------------------------------
class VIEW3D_PT_easy_library(Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_easy_library"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Easy Library'
    bl_order = 100  # This pushes it below other panels

    def draw_header(self, context):
        """Custom header with logo and centered text"""
        layout = self.layout
        
        # Center the header content
        row = layout.row(align=True)
        row.alignment = 'CENTER'
        
        # Get the logo icon
        icon_val = 0
        if custom_icons and "jopex_logo" in custom_icons:
            icon_val = custom_icons["jopex_logo"].icon_id
        
        # Display logo and text together
        if icon_val != 0:
            row.label(text="", icon_value=icon_val)
            row.label(text="Easy Library")
        else:
            row.label(text="Easy Library", icon='ASSET_MANAGER')

    def draw(self, context):
        # Main layout
        layout = self.layout
        
        # Create a box for the grey background
        box = layout.box()
        
        # Add content inside the box
        content = box.column(align=True)
        content.separator(factor=0.3)
        
        props = context.scene.easylib_props

        # Search bar
        row = content.row(align=True)
        row.prop(props, "search_query", icon='VIEWZOOM', text="")
        row.operator(EASYLIB_OT_clear_search.bl_idname, text="", icon='X')
        content.separator()

        # Grid columns
        row = content.row(align=True)
        row.label(text="Grid:", icon='GRID')
        row.prop(props, "grid_columns", text="")
        content.separator()

        if not os.path.exists(ASSETS_DIR):
            content.label(text="Assets folder not found!", icon='ERROR')
            self._draw_management(content)
            self._draw_footer(content)
            content.separator(factor=0.3)
            return

        try:
            categories = sorted([d for d in os.listdir(ASSETS_DIR)
                                  if os.path.isdir(os.path.join(ASSETS_DIR, d))])
        except Exception as e:
            content.label(text=f"Error: {e}", icon='ERROR')
            self._draw_management(content)
            self._draw_footer(content)
            content.separator(factor=0.3)
            return

        if not categories:
            content.label(text="No folders found. Add one below!", icon='INFO')
            self._draw_management(content)
            self._draw_footer(content)
            content.separator(factor=0.3)
            return

        query = props.search_query.lower()
        expanded = set(props.expanded_folders.split("|")) if props.expanded_folders else set()
        valid_exts = ('.blend', '.exr', '.hdr', '.fbx', '.obj', '.glb', '.gltf')

        for category in categories:
            cat_path = os.path.join(ASSETS_DIR, category)
            try:
                all_files = [f for f in os.listdir(cat_path) if f.lower().endswith(valid_exts)]
            except Exception:
                continue

            if query:
                files = [f for f in all_files
                         if query in f.lower() or query in category.lower()]
                if not files:
                    continue
            else:
                files = all_files

            is_open = (category in expanded) or bool(query)
            cat_box = content.box()

            # Folder header
            row = cat_box.row(align=True)
            icon = 'TRIA_DOWN' if is_open else 'TRIA_RIGHT'
            op = row.operator(EASYLIB_OT_toggle_folder.bl_idname,
                               text=category, icon=icon, emboss=False)
            op.folder_name = category

            if is_open and files:
                self._draw_asset_grid(context, cat_box, category, cat_path, files)

        self._draw_management(content)
        self._draw_footer(content)
        content.separator(factor=0.3)

    def _draw_asset_grid(self, context, layout, category, cat_path, files):
        """Draw assets in a responsive grid with uniform thumbnails"""
        props = context.scene.easylib_props
        
        col_count = props.grid_columns

        if col_count == 1:
            icon_scale = 8.0
            fallback_scale = 2.5
        elif col_count == 2:
            icon_scale = 4.5
            fallback_scale = 1.8
        elif col_count == 3:
            icon_scale = 3.0
            fallback_scale = 1.2
        else:
            icon_scale = 2.0
            fallback_scale = 1.0

        main_col = layout.column(align=True)
        current_row = None

        sorted_files = sorted(files)
        for i, file in enumerate(sorted_files):
            if i % col_count == 0:
                current_row = main_col.row()

            file_path = os.path.join(cat_path, file)
            display_name = os.path.splitext(file)[0]

            icon_id = get_icon_id(file_path, display_name, cat_path)

            box = current_row.box()
            inner = box.column(align=True)

            label = display_name[:15] + "..." if len(display_name) > 15 else display_name

            if icon_id != 0:
                icon_row = inner.row(align=True)
                icon_row.alignment = 'CENTER'
                icon_row.template_icon(icon_value=icon_id, scale=icon_scale)

                op_row = inner.row(align=True)
                op_row.scale_y = 1.0
                op = op_row.operator(
                    EASYLIB_OT_add_asset.bl_idname,
                    text=label
                )
            else:
                ext = os.path.splitext(file)[1].lower()
                if ext == '.blend':
                    icon_type = 'FILE_BLEND'
                elif ext in ['.exr', '.hdr']:
                    icon_type = 'IMAGE_RGB'
                else:
                    icon_type = 'FILE_3D'
                
                btn_row = inner.row(align=True)
                btn_row.scale_y = fallback_scale
                
                op = btn_row.operator(
                    EASYLIB_OT_add_asset.bl_idname,
                    text=label,
                    icon=icon_type
                )

            op.file_path = file_path
            op.display_name = display_name

        remainder = len(sorted_files) % col_count
        if remainder != 0 and current_row is not None:
            for _ in range(col_count - remainder):
                spacer = current_row.column()
                spacer.label(text="")

    def _draw_management(self, layout):
        layout.separator()
        box = layout.box()
        row = box.row(align=True)
        row.operator(EASYLIB_OT_add_asset_file.bl_idname, text="Add Asset", icon='IMPORT')
        row.operator(EASYLIB_OT_remove_asset_dialog.bl_idname, text="Remove Asset", icon='TRASH')
        row = box.row(align=True)
        row.operator(EASYLIB_OT_add_folder.bl_idname, text="Add Folder", icon='NEWFOLDER')
        row.operator(EASYLIB_OT_remove_folder.bl_idname, text="Remove Folder", icon='X')
        row = box.row(align=True)
        row.operator(EASYLIB_OT_move_asset.bl_idname, text="Move Asset", icon='FOLDER_REDIRECT')
        row.operator(EASYLIB_OT_rename_asset.bl_idname, text="Rename Asset", icon='OUTLINER_DATA_FONT')
        row = box.row(align=True)
        row.operator(EASYLIB_OT_rename_folder.bl_idname, text="Rename Folder", icon='OUTLINER_DATA_FONT')

    def _draw_footer(self, layout):
        layout.separator()
        box = layout.box()
        col = box.column(align=True)
        for text in ["Developed By", "Jopex Creatives", "jopexcreatives@gmail.com"]:
            row = col.row()
            row.alignment = 'CENTER'
            if text == "Jopex Creatives":
                row.label(text=text, icon='USER')
            else:
                row.label(text=text)

# -----------------------------------------------------------------
#  Registration
# -----------------------------------------------------------------
classes = [
    EasyLibraryPreferences,
    EasyLibraryProps,
    EASYLIB_OT_open_readme,
    EASYLIB_OT_confirm_action,
    EASYLIB_OT_add_folder,
    EASYLIB_OT_remove_folder,
    EASYLIB_OT_rename_folder,
    EASYLIB_OT_add_asset_file,
    EASYLIB_OT_remove_asset_dialog,
    EASYLIB_OT_move_asset,
    EASYLIB_OT_rename_asset,
    EASYLIB_OT_clear_search,
    EASYLIB_OT_toggle_folder,
    EASYLIB_OT_add_asset,
    VIEW3D_PT_easy_library,
]

def register():
    register_custom_icons()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.easylib_props = PointerProperty(type=EasyLibraryProps)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "easylib_props"):
        del bpy.types.Scene.easylib_props
    clear_previews()
    unregister_custom_icons()

if __name__ == "__main__":
    register()