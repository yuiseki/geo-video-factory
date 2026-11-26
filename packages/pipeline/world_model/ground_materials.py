"""Aged road materials for the Blender projection test (bpy only; no lamps in the scene).

Both materials are a Principled BSDF (so wet patches reflect the emissive photo facades through EEVEE's
ray tracing) plus a weak emission of the albedo (stand-in for ambient light, the scene has no lamps).
All patterns use world position, so neighbouring quads and the ground agree.

aged_asphalt: grain + low-frequency mottling + patched repairs (Voronoi cells of another shade) + tyre
              tracks (noise stretched along one axis) + wet patches (low roughness, darker albedo).
worn_paint:   zebra paint with holes where it has worn off, scuffs, grime; under the holes, asphalt.
"""
import bpy


class G:
    def __init__(self, name):
        self.m = bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        for nd in list(self.nt.nodes):
            if nd.type != "OUTPUT_MATERIAL":
                self.nt.nodes.remove(nd)
        geo = self.nt.nodes.new("ShaderNodeNewGeometry")
        self.pos = geo.outputs["Position"]

    def node(self, kind, **inputs):
        n = self.nt.nodes.new(kind)
        for k, v in inputs.items():
            if hasattr(v, "is_output"):
                self.nt.links.new(v, n.inputs[k])
            else:
                n.inputs[k].default_value = v
        return n

    def noise(self, scale, detail=4.0, stretch=None):
        vec = self.pos
        if stretch:
            mp = self.node("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = stretch
            self.nt.links.new(self.pos, mp.inputs["Vector"])
            vec = mp.outputs[0]
        return self.node("ShaderNodeTexNoise", Vector=vec, Scale=scale, Detail=detail).outputs["Fac"]

    def math(self, op, a, b=None, clamp=False):
        n = self.nt.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if hasattr(v, "is_output"):
                self.nt.links.new(v, n.inputs[i])
            else:
                n.inputs[i].default_value = v
        return n.outputs[0]

    def band(self, x, lo, hi):
        """0 below lo, 1 above hi, smooth between."""
        n = self.node("ShaderNodeMapRange", Value=x)
        n.interpolation_type = "SMOOTHSTEP"
        n.inputs["From Min"].default_value = lo
        n.inputs["From Max"].default_value = hi
        return n.outputs["Result"]

    def finish(self, value, roughness, tint=(1.0, 0.98, 0.95), glow=1.0):
        col = self.node("ShaderNodeCombineColor")
        for i in range(3):
            self.nt.links.new(self.math("MULTIPLY", value, tint[i]), col.inputs[i])
        bsdf = self.node("ShaderNodeBsdfPrincipled", Roughness=roughness)
        self.nt.links.new(col.outputs[0], bsdf.inputs["Base Color"])
        em = self.node("ShaderNodeEmission", Strength=glow)
        self.nt.links.new(col.outputs[0], em.inputs["Color"])
        add = self.node("ShaderNodeAddShader")
        self.nt.links.new(bsdf.outputs[0], add.inputs[0])
        self.nt.links.new(em.outputs[0], add.inputs[1])
        self.nt.links.new(add.outputs[0], self.nt.nodes["Material Output"].inputs["Surface"])
        return self.m


def _asphalt_value(g, wetness=1.0):
    """(albedo value, wet mask) shared by both materials. wetness 0 is a dry road (no mirror patches)."""
    grain = g.noise(55, 2)
    mottle = g.noise(0.12, 6)
    # repaired patches, each its own shade: about 11 m across and faint, or from above they read as the facets of a mesh
    vor = g.node("ShaderNodeTexVoronoi", Vector=g.pos, Scale=0.09)
    tone = g.math("MULTIPLY", g.node("ShaderNodeSeparateColor", Color=vor.outputs["Color"]).outputs[0], 0.006)
    tracks = g.band(g.noise(1.0, 3, stretch=(0.35, 7.0, 1.0)), 0.55, 0.7)
    v = g.math("ADD", 0.028, g.math("MULTIPLY", mottle, 0.022))
    v = g.math("ADD", v, g.math("MULTIPLY", grain, 0.016))
    v = g.math("ADD", v, tone)
    v = g.math("SUBTRACT", v, g.math("MULTIPLY", tracks, 0.012))
    # puddles a few metres across: tens of metres of mirror show the dark sky and read as holes from above
    wet = g.math("MULTIPLY", g.band(g.noise(0.2, 3), 0.60, 0.64), wetness)
    v = g.math("MULTIPLY", v, g.math("SUBTRACT", 1.0, g.math("MULTIPLY", wet, 0.45)))
    return v, wet


def aged_asphalt(gain=1.0, glow=1.0, wetness=1.0):
    """gain multiplies the albedo (the night values are those of a street lit by signs; daylight needs
    about 1.5x under a sun lamp), glow is the strength of the stand-in ambient emission (lower it when a sun lamp lights)."""
    g = G("aged_asphalt")
    v, wet = _asphalt_value(g, wetness)
    rough = g.math("SUBTRACT", 0.9, g.math("MULTIPLY", wet, 0.8))
    return g.finish(g.math("MULTIPLY", v, gain), rough, tint=(0.95, 0.96, 1.0), glow=glow)


def worn_paint(gain=1.0, glow=1.0, wetness=1.0):
    g = G("worn_paint")
    base, wet = _asphalt_value(g, wetness)
    holes = g.band(g.noise(2.6, 8), 0.40, 0.47)                      # 1 where paint remains
    scuff = g.band(g.noise(0.8, 3, stretch=(0.25, 6.0, 1.0)), 0.5, 0.75)   # tyre-worn lanes
    cover = g.math("MULTIPLY", holes, g.math("SUBTRACT", 1.0, g.math("MULTIPLY", scuff, 0.7)))
    grime = g.math("MULTIPLY", g.noise(9, 6), 0.06)
    paint = g.math("SUBTRACT", 0.17, grime)
    v = g.math("ADD", g.math("MULTIPLY", base, g.math("SUBTRACT", 1.0, cover)), g.math("MULTIPLY", paint, cover))
    rough = g.math("SUBTRACT", g.math("ADD", 0.9, g.math("MULTIPLY", cover, -0.35)), g.math("MULTIPLY", wet, 0.5))
    return g.finish(g.math("MULTIPLY", v, gain), rough, tint=(0.98, 0.98, 0.96), glow=glow)
