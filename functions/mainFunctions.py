import bpy
import numpy
from math import pi
from mathutils import Matrix
from .jsonFunctions import objectDataToDico

from .. import __package__


def getPreferences(context):
    return context.preferences.addons[__package__].preferences


def createViewLayerCollection(context):
    bw_collection_name = getPreferences(context).bonewidget_collection_name

    # if it exists but not linked to scene
    collection = bpy.data.collections.get(bw_collection_name)
    if collection is None:
        collection = bpy.data.collections.new(bw_collection_name)
    context.scene.collection.children.link(collection)

    # hide new collection
    viewlayer_collection = context.view_layer.layer_collection.children[collection.name]
    viewlayer_collection.hide_viewport = True

    return viewlayer_collection


def getCollection(context, query=False):
    viewlayer_collection = getViewLayerCollection(context, query=query)
    collection = None
    if viewlayer_collection is not None: # anticipate query
        collection = viewlayer_collection.collection
    # make sure the collection is not excluded
    return collection


def getViewLayerCollection(context, widget=None, query=False):
    bw_collection_name = getPreferences(context).bonewidget_collection_name
    viewlayer_collection = None

    # prioritize search from widget if specified, otherwise look at current object first.
    if widget is None and context.object and context.object.type == "ARMATURE":
        for bone in context.object.pose.bones:
            widget = bone.custom_shape
            if widget is not None:
                break

    if widget is not None:
        lc_list = [context.view_layer.layer_collection]
        while len(lc_list) > 0:
            lc = lc_list.pop()
            if widget.name in lc.collection.objects:
                viewlayer_collection = lc
            else:
                lc_list.extend(child_lc for child_lc in lc.children)

    if viewlayer_collection is None:
        viewlayer_collection = context.view_layer.layer_collection.children.get(bw_collection_name)
        if viewlayer_collection is None and not query:
            # if there's no viewlayer_collection found, create one.
            viewlayer_collection = createViewLayerCollection(context)

    # make sure the collection is not excluded
    if not query:
        viewlayer_collection.exclude = False
    return viewlayer_collection


def boneMatrix(widget, matchBone):
    if widget == None:
        return
    widget.matrix_local = matchBone.bone.matrix_local
    widget.matrix_world = matchBone.id_data.matrix_world @ matchBone.bone.matrix_local
    if matchBone.custom_shape_transform:
        #if it has a tranform override apply this to the widget loc and rot
        org_scale = widget.matrix_world.to_scale()
        org_scale_mat = Matrix.Scale(1, 4, org_scale)
        target_matrix = matchBone.custom_shape_transform.id_data.matrix_world @ matchBone.custom_shape_transform.bone.matrix_local
        loc = target_matrix.to_translation()
        loc_mat  = Matrix.Translation(loc)
        rot = target_matrix.to_euler().to_matrix()
        widget.matrix_world = loc_mat @ rot.to_4x4() @ org_scale_mat

    if matchBone.use_custom_shape_bone_size:
        ob_scale = bpy.context.scene.objects[matchBone.id_data.name].scale
        widget.scale = [matchBone.bone.length * ob_scale[0], matchBone.bone.length * ob_scale[1], matchBone.bone.length * ob_scale[2]]
        #widget.scale = [matchBone.bone.length, matchBone.bone.length, matchBone.bone.length]
    widget.data.update()


def fromWidgetFindBone(widget):
    matchBone = None
    for ob in bpy.context.scene.objects:
        if ob.type == "ARMATURE":
            for bone in ob.pose.bones:
                if bone.custom_shape == widget:
                    matchBone = bone
    return matchBone


def createWidget(bone, widget, relative, size, scale, slide, rotation, collection):
    C = bpy.context
    D = bpy.data
    bw_widget_prefix = getPreferences(C).widget_prefix

#     if bone.custom_shape_transform:
#    matrixBone = bone.custom_shape_transform
#     else:
    matrixBone = bone

    if bone.custom_shape:
        bone.custom_shape.name = bone.custom_shape.name + "_old"
        bone.custom_shape.data.name = bone.custom_shape.data.name + "_old"
        if C.scene.collection.objects.get(bone.custom_shape.name):
            C.scene.collection.objects.unlink(bone.custom_shape)

    # make the data name include the prefix
    newData = D.meshes.new(bw_widget_prefix + bone.name)

    if relative is True:
        boneLength = 1
    else:
        boneLength = (1 / bone.bone.length)

    # add the verts
    newData.from_pydata(numpy.array(widget['vertices']) * [size * scale[0] * boneLength, size * scale[2]
                        * boneLength, size * scale[1] * boneLength], widget['edges'], widget['faces'])

    # Create tranform matrices (slide vector and rotation)
    widget_matrix = Matrix()
    trans = Matrix.Translation((0, slide, 0))
    rot = rotation.to_matrix().to_4x4()

    # Translate then rotate the matrix
    widget_matrix = widget_matrix @ trans
    widget_matrix = widget_matrix @ rot

    # transform the widget with this matrix
    newData.transform(widget_matrix)

    newData.update(calc_edges=True)

    newObject = D.objects.new(bw_widget_prefix + bone.name, newData)

    newObject.data = newData
    newObject.name = bw_widget_prefix + bone.name
    collection.objects.link(newObject)

    newObject.matrix_world = bpy.context.active_object.matrix_world @ matrixBone.bone.matrix_local
    newObject.scale = [matrixBone.bone.length, matrixBone.bone.length, matrixBone.bone.length]
    layer = bpy.context.view_layer
    layer.update()

    bone.custom_shape = newObject
    bone.bone.show_wire = True


def symmetrizeWidget(bone, collection):
    C = bpy.context
    D = bpy.data
    bw_widget_prefix = getPreferences(C).widget_prefix

    widget = bone.custom_shape

    if findMirrorObject(bone) is not None:
        if findMirrorObject(bone).custom_shape_transform:
            mirrorBone = findMirrorObject(bone).custom_shape_transform
        else:
            mirrorBone = findMirrorObject(bone)

        mirrorWidget = mirrorBone.custom_shape

        if mirrorWidget:
            if mirrorWidget != widget:
                mirrorWidget.name = mirrorWidget.name + "_old"
                mirrorWidget.data.name = mirrorWidget.data.name + "_old"
                # unlink/delete old widget
                if C.scene.objects.get(mirrorWidget.name):
                    D.objects.remove(mirrorWidget)

        newData = widget.data.copy()
        for vert in newData.vertices:
            vert.co = numpy.array(vert.co) * (-1, 1, 1)

        newObject = widget.copy()
        newObject.data = newData
        newData.update()
        newObject.name = bw_widget_prefix + mirrorBone.name
        collection.objects.link(newObject)
        newObject.matrix_local = mirrorBone.bone.matrix_local
        newObject.scale = [mirrorBone.bone.length, mirrorBone.bone.length, mirrorBone.bone.length]

        layer = bpy.context.view_layer
        layer.update()

        mirrorBone.custom_shape = newObject
        mirrorBone.bone.show_wire = True
    else:
        pass


def symmetrizeWidget_helper(bone, collection, activeObject, widgetsAndBones):
    C = bpy.context

    bw_symmetry_suffix = getPreferences(C).symmetry_suffix
    bw_symmetry_suffix = bw_symmetry_suffix.split(";")

    suffix_1 = bw_symmetry_suffix[0].replace(" ", "")
    suffix_2 = bw_symmetry_suffix[1].replace(" ", "")

    if activeObject.name.endswith(suffix_1):
        if bone.name.endswith(suffix_1) and widgetsAndBones[bone]:
            symmetrizeWidget(bone, collection)
    elif activeObject.name.endswith(suffix_2):
        if bone.name.endswith(suffix_2) and widgetsAndBones[bone]:
            symmetrizeWidget(bone, collection)


def deleteUnusedWidgets():
    C = bpy.context
    D = bpy.data

    collection = getCollection(C, query=True)
    if collection is None:
        return []

    widgetList = []

    for ob in D.objects:
        if ob.type == 'ARMATURE':
            for bone in ob.pose.bones:
                if bone.custom_shape:
                    widgetList.append(bone.custom_shape)

    unwantedList = [ob for ob in collection.all_objects if ob not in widgetList]
    # save the current context mode
    mode = C.mode
    # jump into object mode
    bpy.ops.object.mode_set(mode='OBJECT')
    # delete unwanted widgets
    bpy.ops.object.delete({"selected_objects": unwantedList})
    # jump back to current mode
    bpy.ops.object.mode_set(mode=mode)

    return unwantedList


def editWidget(active_bone):
    C = bpy.context
    D = bpy.data
    widget = active_bone.custom_shape

    armature = active_bone.id_data
    bpy.ops.object.mode_set(mode='OBJECT')
    C.active_object.select_set(False)

    # we may get a customshape setup where it's hidden at collection or viewlayer_collection level.
    viewlayer_collection = getViewLayerCollection(C, widget)
    collection = viewlayer_collection.collection
    viewlayer_collection.hide_viewport = False
    collection.hide_viewport = False

    # if widget is unlinked from scene, relink to default widget collection
    if widget.name not in collection.objects:
        collection.objects.link(widget)

    if C.space_data.local_view:
        bpy.ops.view3d.localview()

    # select object and make it active
    widget.select_set(True)
    bpy.context.view_layer.objects.active = widget
    bpy.ops.object.mode_set(mode='EDIT')


def copyWidget(active_bone, selected_bones):
    for bone in selected_bones:
        if bone != active_bone:
            bone.custom_shape = active_bone.custom_shape


def returnToArmature(widget):
    C = bpy.context
    D = bpy.data

    bone = fromWidgetFindBone(widget)
    armature = bone.id_data

    if C.active_object.mode == 'EDIT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')

    viewlayer_collection = getViewLayerCollection(C, widget)
    viewlayer_collection.hide_viewport = True
    if C.space_data.local_view:
        bpy.ops.view3d.localview()
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    armature.data.bones[bone.name].select = True
    armature.data.bones.active = armature.data.bones[bone.name]


def findMirrorObject(object):
    C = bpy.context
    D = bpy.data

    bw_symmetry_suffix = getPreferences(C).symmetry_suffix
    bw_symmetry_suffix = bw_symmetry_suffix.split(";")

    suffix_1 = bw_symmetry_suffix[0].replace(" ", "")
    suffix_2 = bw_symmetry_suffix[1].replace(" ", "")

    if object.name.endswith(suffix_1):
        suffix = suffix_2
        suffix_length = len(suffix_1)

    elif object.name.endswith(suffix_2):
        suffix = suffix_1
        suffix_length = len(suffix_2)

    elif object.name.endswith(suffix_1.lower()):
        suffix = suffix_2.lower()
        suffix_length = len(suffix_1)
    elif object.name.endswith(suffix_2.lower()):
        suffix = suffix_1.lower()
        suffix_length = len(suffix_2)
    else:  # what if the widget ends in .001?
        print('Object suffix unknown, using blank')
        suffix = ''

    objectName = list(object.name)
    objectBaseName = objectName[:-suffix_length]
    mirroredObjectName = "".join(objectBaseName) + suffix

    if object.id_data.type == 'ARMATURE':
        return object.id_data.pose.bones.get(mirroredObjectName)
    else:
        return bpy.context.scene.objects.get(mirroredObjectName)


def findMatchBones():
    C = bpy.context
    D = bpy.data

    bw_symmetry_suffix = getPreferences(C).symmetry_suffix
    bw_symmetry_suffix = bw_symmetry_suffix.split(";")

    suffix_1 = bw_symmetry_suffix[0].replace(" ", "")
    suffix_2 = bw_symmetry_suffix[1].replace(" ", "")

    widgetsAndBones = {}

    if bpy.context.object.type == 'ARMATURE':
        for bone in C.selected_pose_bones:
            if bone.name.endswith(suffix_1) or bone.name.endswith(suffix_2):
                widgetsAndBones[bone] = bone.custom_shape
                mirrorBone = findMirrorObject(bone)
                if mirrorBone:
                    widgetsAndBones[mirrorBone] = mirrorBone.custom_shape

        armature = bpy.context.object
        activeObject = C.active_pose_bone
    else:
        for shape in C.selected_objects:
            bone = fromWidgetFindBone(shape)
            if bone.name.endswith(("L","R")):
                widgetsAndBones[fromWidgetFindBone(shape)] = shape

                mirrorShape = findMirrorObject(shape)
                if mirrorShape:
                    widgetsAndBones[mirrorShape] = mirrorShape

        activeObject = fromWidgetFindBone(C.object)
        armature = activeObject.id_data
    return (widgetsAndBones, activeObject, armature)


def resyncWidgetNames():
    C = bpy.context
    D = bpy.data

    bw_collection_name = getPreferences(C).bonewidget_collection_name
    bw_widget_prefix = getPreferences(C).widget_prefix

    widgetsAndBones = {}

    if bpy.context.object.type == 'ARMATURE':
        for bone in C.active_object.pose.bones:
            if bone.custom_shape:
                widgetsAndBones[bone] = bone.custom_shape

    for k, v in widgetsAndBones.items():
        if k.name != (bw_widget_prefix + k.name):
            D.objects[v.name].name = str(bw_widget_prefix + k.name)


def clearBoneWidgets():
    C = bpy.context
    D = bpy.data

    if bpy.context.object.type == 'ARMATURE':
        for bone in C.selected_pose_bones:
            if bone.custom_shape:
                bone.custom_shape = None
                bone.custom_shape_transform = None


def addObjectAsWidget(context, collection):
    sel = bpy.context.selected_objects
    #bw_collection = getPreferences(context).bonewidget_collection_name

    if sel[1].type == 'MESH':
        active_bone = context.active_pose_bone
        widget_object = sel[1]

        # deal with any existing shape
        if active_bone.custom_shape:
            active_bone.custom_shape.name = active_bone.custom_shape.name + "_old"
            active_bone.custom_shape.data.name = active_bone.custom_shape.data.name + "_old"
            if C.scene.collection.objects.get(active_bone.custom_shape.name):
                C.scene.collection.objects.unlink(active_bone.custom_shape)

        #duplicate shape
        widget = widget_object.copy()
        widget.data = widget.data.copy()
        # reamame it
        bw_widget_prefix = getPreferences(context).widget_prefix
        widget_name = bw_widget_prefix + active_bone.name
        widget.name = widget_name
        widget.data.name = widget_name
        # link it
        collection.objects.link(widget)

        # match transforms
        widget.matrix_world = bpy.context.active_object.matrix_world @ active_bone.bone.matrix_local
        widget.scale = [active_bone.bone.length, active_bone.bone.length, active_bone.bone.length]
        layer = bpy.context.view_layer
        layer.update()

        active_bone.custom_shape = widget
        active_bone.bone.show_wire = True

        #deselect original object
        widget_object.select_set(False)
