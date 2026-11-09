// build_clip.jsx - one MoonPay clip in AE 2025 from PLAN (written by clip_build.py ae).
// Layers (bottom -> top): blurred fill, speaker footage (face-anchored scale keys, optional drop + top feather mask),
// Premium Glow CC adjustment layer (the user's .ffx), caption overlay (alpha mov from captions.py ASS), title PNG.
(function () {
    var P = PLAN;
    function log(s) { _aelog(s); }
    try {
        app.beginSuppressDialogs();
        if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        app.newProject();
        var proj = app.project;
        function imp(path) { var f = new File(path); if (!f.exists) throw new Error("missing " + path); return proj.importFile(new ImportOptions(f)); }
        var foot = imp(P.footage); foot.mainSource.conformFrameRate = P.fps;
        var capI = imp(P.captions); capI.mainSource.conformFrameRate = P.fps; capI.mainSource.alphaMode = AlphaMode.STRAIGHT;
        var titI = imp(P.title);
        var dur = P.frames / P.fps;
        var comp = proj.items.addComp(P.name, P.W, P.H, 1, dur, P.fps);
        comp.bgColor = [0, 0, 0];
        comp.motionBlur = false;
        log("comp " + comp.width + "x" + comp.height + " " + comp.frameRate + " fps, " + P.frames + " f");

        // 1. blurred fill (only seen where the footage is dropped / feathered)
        var bg = comp.layers.add(foot); bg.name = "BG blur fill"; bg.quality = LayerQuality.BEST;
        bg.property("ADBE Transform Group").property("ADBE Scale").setValue([140, 140]);
        bg.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([P.anchor[0], P.anchor[1]]);
        bg.property("ADBE Transform Group").property("ADBE Position").setValue([P.W / 2, P.anchor[1] + 900]);
        var gb = bg.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2");
        gb.property(1).setValue(120); gb.property(3).setValue(1);
        var bc = bg.property("ADBE Effect Parade").addProperty("ADBE Brightness & Contrast 2");
        bc.property(1).setValue(-50);
        bg.enabled = (P.drop > 0 || P.mask_top > 0);

        // 2. speaker footage, scale keys about the face anchor
        var L = comp.layers.add(foot); L.name = "Speaker"; L.quality = LayerQuality.BEST;
        var tr = L.property("ADBE Transform Group");
        tr.property("ADBE Anchor Point").setValue([P.anchor[0], P.anchor[1]]);
        tr.property("ADBE Position").setValue([P.anchor[0], P.anchor[1] + P.drop]);
        var sc = tr.property("ADBE Scale");
        var ts = [], vs = [];
        for (var i = 0; i < P.scale_keys.length; i++) { ts.push(P.scale_keys[i][0] / P.fps); vs.push([P.scale_keys[i][1], P.scale_keys[i][1]]); }
        sc.setValuesAtTimes(ts, vs);
        if (P.drop > 0 || P.mask_top > 0) {
            var m = L.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            var sh = new Shape();
            var y0 = P.mask_top;
            sh.vertices = [[-400, y0], [P.W + 400, y0], [P.W + 400, P.H + 800], [-400, P.H + 800]];
            sh.closed = true;
            m.property("ADBE Mask Shape").setValue(sh);
            m.property("ADBE Mask Feather").setValue([0, P.feather]);
        }
        log("footage ok, scale keys " + ts.length + ", drop " + P.drop + ", mask_top " + P.mask_top);

        // 3. grade: the user's Premium Glow CC preset on an adjustment layer above the footage only
        var adj = comp.layers.addSolid([1, 1, 1], "Premium Glow CC", P.W, P.H, 1, dur);
        adj.adjustmentLayer = true;
        adj.applyPreset(new File(P.preset));
        var fx = adj.property("ADBE Effect Parade");
        var names = [];
        for (var k = 1; k <= fx.numProperties; k++) names.push(fx.property(k).matchName);
        log("grade fx: " + names.join(", "));
        if (P.grade && P.grade.lumetri) {
            var lum = fx.property("ADBE Lumetri");
            for (var key in P.grade.lumetri) { lum.property(key).setValue(P.grade.lumetri[key]); log("lumetri " + key + " = " + P.grade.lumetri[key]); }
        }
        if (P.grade && P.grade.bc) {
            var b2 = fx.property("ADBE Brightness & Contrast 2");
            b2.property(1).setValue(P.grade.bc[0]); b2.property(2).setValue(P.grade.bc[1]);
        }

        // 4. captions (pre-laid-out + gated by captions.py, ASS rendered to alpha)
        var cap = comp.layers.add(capI); cap.name = "Captions"; cap.quality = LayerQuality.BEST;

        // 5. title (one line, whole clip, quick pop in)
        var tl = comp.layers.add(titI); tl.name = "Title"; tl.quality = LayerQuality.BEST;
        var ttr = tl.property("ADBE Transform Group");
        ttr.property("ADBE Anchor Point").setValue([P.W / 2, P.title_cy_png]);
        ttr.property("ADBE Position").setValue([P.W / 2, P.title_cy]);
        var f = 1 / P.fps;
        ttr.property("ADBE Scale").setValuesAtTimes([0, 3 * f, 6 * f], [[88, 88], [103, 103], [100, 100]]);
        ttr.property("ADBE Opacity").setValuesAtTimes([0, 3 * f], [0, 100]);

        // render queue: H.264 40 Mbps, video only (audio is muxed by finalize_mux.py)
        var rq = proj.renderQueue.items.add(comp);
        rq.applyTemplate("Best Settings");
        var om = rq.outputModule(1);
        om.applyTemplate("H.264 - Match Render Settings - 40 Mbps");
        om.file = new File(P.out_video);
        proj.save(new File(P.aep));
        log("saved " + P.aep);
        log("BUILD_OK");
    } catch (e) {
        log("BUILD_ERROR " + e.toString() + " line " + e.line);
    }
})();
