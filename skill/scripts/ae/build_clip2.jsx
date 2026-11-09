// build_clip2.jsx - a whole brand-campaign clip edit in AE 2025 from PLAN (written by the job driver's ae stage).
// Bottom -> top: blurred fill | CAM null (drop + push/punch about the face) > speaker footage with per-frame face
// stabilisation keys (face_track.py steady on the Topaz footage) | Premium Glow CC adjustment layer |
// captions = one text layer per word (layout from captions.py: safe area + face-clear), stroke + shadow,
// Deep Glow 2 on keywords, pop-in | title card = shape box + text with the product names in purple.
(function () {
    var P = PLAN;
    function log(s) { _aelog(s); }
    function hex(h) { h = h.replace("#", ""); return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
    function TG(l) { return l.property("ADBE Transform Group"); }
    try {
        app.beginSuppressDialogs();
        if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        app.newProject();
        var proj = app.project;
        function imp(path) { var f = new File(path); if (!f.exists) throw new Error("missing " + path); return proj.importFile(new ImportOptions(f)); }
        var foot = imp(P.footage); foot.mainSource.conformFrameRate = P.fps;
        var dur = P.frames / P.fps, f1 = 1 / P.fps;
        var comp = proj.items.addComp(P.name, P.W, P.H, 1, dur, P.fps);
        comp.bgColor = [0, 0, 0]; comp.motionBlur = false;

        // 1. blurred fill (only seen above a dropped / masked footage layer): a 340 % blow-up of the backdrop beside the
        //    face (the side away from it), so the band above the footage is the scene's colour, never black or a ghost face
        //    The blow-up lives in a canvas-size precomp: a 340 % layer straight in the comp made AE hand Sapphire S_Sharpen
        //    (preset adjustment layer) a ~3.7k x 6.5k blurred input and aerender committed 16-19 GB per frame.
        var bgc = proj.items.addComp(P.name + " BG", P.W, P.H, 1, dur, P.fps);
        var bgl = bgc.layers.add(foot); bgl.quality = LayerQuality.BEST;
        // anchor 180 px in from the edge: the 340 % layer still covers 0..W (540 - 180*3.4 < 0) and the face maps off-canvas
        var bx = (P.anchor[0] > P.W / 2) ? 180 : P.W - 180;
        TG(bgl).property("ADBE Scale").setValue([340, 340]);
        TG(bgl).property("ADBE Anchor Point").setValue([bx, (P.bg_y !== undefined) ? P.bg_y : P.anchor[1]]);
        TG(bgl).property("ADBE Position").setValue([P.W / 2, 300]);
        if (P.bg_color) { var bgs = bgc.layers.addSolid(P.bg_color, "backdrop colour", P.W, P.H, 1, dur); TG(bgs).property("ADBE Opacity").setValue(75); }
        var bg = comp.layers.add(bgc); bg.name = "BG blur fill"; bg.quality = LayerQuality.BEST;
        var gb = bg.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2"); gb.property(1).setValue(120); gb.property(3).setValue(1);
        bg.property("ADBE Effect Parade").addProperty("ADBE Brightness & Contrast 2").property(1).setValue(-30);
        bg.enabled = (P.drop > 0 || P.mask_top > 0);

        // 2. CAM null: drop + slow push + punch-ins, scaled about the face anchor
        var cam = comp.layers.addNull(dur); cam.name = "CAM (push / punch)";
        TG(cam).property("ADBE Opacity").setValue(100);
        TG(cam).property("ADBE Anchor Point").setValue([50, 50]);
        TG(cam).property("ADBE Position").setValue([P.anchor[0], P.anchor[1] + P.drop]);
        var ts = [], vs = [];
        for (var i = 0; i < P.scale_keys.length; i++) { ts.push(P.scale_keys[i][0] / P.fps); vs.push([P.scale_keys[i][1], P.scale_keys[i][1]]); }
        TG(cam).property("ADBE Scale").setValuesAtTimes(ts, vs);

        // 3. footage with the face tracking / stabilising keys (one key per frame), parented to CAM
        var L = comp.layers.add(foot); L.name = "Speaker (face-stabilised)"; L.quality = LayerQuality.BEST;
        L.parent = cam;
        var st = P.stab, pt = [], pv = [], sv = [];
        for (var k = 0; k < st.position.length; k++) {
            pt.push(k / P.fps);
            // stabiliser position is in canvas px; re-express it in CAM's space (CAM sits at the face anchor)
            pv.push([st.position[k][0] - P.anchor[0] + 50, st.position[k][1] - P.anchor[1] + 50]);
            sv.push([st.scale[k], st.scale[k]]);
        }
        TG(L).property("ADBE Anchor Point").setValue([st.anchor[0], st.anchor[1]]);
        TG(L).property("ADBE Position").setValuesAtTimes(pt, pv);
        TG(L).property("ADBE Scale").setValuesAtTimes(pt, sv);
        if (P.drop > 0 || P.mask_top > 0) {
            var m = L.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
            var sh = new Shape(); var y0 = P.mask_top;
            sh.vertices = [[-400, y0], [P.W + 400, y0], [P.W + 400, P.H + 800], [-400, P.H + 800]]; sh.closed = true;
            m.property("ADBE Mask Shape").setValue(sh); m.property("ADBE Mask Feather").setValue([0, P.feather]);
        }
        log("footage: stab keys " + pt.length + " (" + P.stab_mode + "), cam keys " + ts.length + ", drop " + P.drop + ", mask_top " + P.mask_top);

        // 3a. punch-ins on wide stage shots: a ZOOM null above CAM, scaled about the face centre, cutting in and out on
        //     the shot's own edges (hold keys) so the face reads on a phone without touching the close-ups
        if (P.zooms && P.zooms.length) {
            var zm0 = P.zooms[0];
            var ZM = comp.layers.addNull(dur); ZM.name = "ZOOM (wide-shot punch-ins)";
            TG(ZM).property("ADBE Anchor Point").setValue([50, 50]);
            TG(ZM).property("ADBE Position").setValue([zm0.cx, zm0.cy]);
            cam.parent = ZM;
            var zt = [0], zv = [[100, 100]];
            for (var zi = 0; zi < P.zooms.length; zi++) {
                var zz = P.zooms[zi];
                zt.push(zz.f0 * f1); zv.push([zz.scale, zz.scale]);
                zt.push((zz.f1 + 1) * f1); zv.push([100, 100]);
            }
            var zsc = TG(ZM).property("ADBE Scale");
            zsc.setValuesAtTimes(zt, zv);
            for (var zk = 1; zk <= zsc.numKeys; zk++) zsc.setInterpolationTypeAtKey(zk, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
            log("zoom null: " + P.zooms.length + " punch-in(s) about " + zm0.cx + "," + zm0.cy);
        }

        // 3b. freeze-frames over a span (e.g. a branded audience cutaway in the source): hold frame src at its own
        //     stabilised position, with a slow 6 % push-in so the hold reads as a deliberate move
        for (var z = 0; P.freezes && z < P.freezes.length; z++) {
            var fz = P.freezes[z], Fz = L.duplicate();
            Fz.name = "freeze f" + fz.f0 + "-" + fz.f1 + " (holds f" + fz.src + ")";
            var zp = TG(L).property("ADBE Position").valueAtTime(fz.src * f1, false), zs = TG(L).property("ADBE Scale").valueAtTime(fz.src * f1, false);
            Fz.timeRemapEnabled = true;
            var trm = Fz.property("ADBE Time Remapping");
            while (trm.numKeys > 1) trm.removeKey(trm.numKeys);   // one key = a held frame (removing all keys hides it)
            trm.setValueAtKey(1, fz.src * f1);
            var zP = TG(Fz).property("ADBE Position"), zS = TG(Fz).property("ADBE Scale");
            while (zP.numKeys) zP.removeKey(1); while (zS.numKeys) zS.removeKey(1);
            zP.setValue(zp);
            zS.setValuesAtTimes([fz.f0 * f1, (fz.f1 + 1) * f1], [[zs[0], zs[1]], [zs[0] * 1.06, zs[1] * 1.06]]);
            Fz.inPoint = fz.f0 * f1; Fz.outPoint = (fz.f1 + 1) * f1;
            log("freeze " + Fz.name + " pos " + Math.round(zp[0]) + "," + Math.round(zp[1]) + " scale " + zs[0].toFixed(1));
        }

        // 4. grade: the user's Premium Glow CC preset (footage only - text sits above it)
        var adj = comp.layers.addSolid([1, 1, 1], "Premium Glow CC", P.W, P.H, 1, dur);
        adj.adjustmentLayer = true; adj.applyPreset(new File(P.preset));
        var fx = adj.property("ADBE Effect Parade"), names = [];
        for (var q = 1; q <= fx.numProperties; q++) names.push(fx.property(q).matchName);
        log("grade fx: " + names.join(", "));
        if (P.grade && P.grade.lumetri) { var lum = fx.property("ADBE Lumetri"); for (var key in P.grade.lumetri) { lum.property(key).setValue(P.grade.lumetri[key]); log("lumetri " + key + " = " + P.grade.lumetri[key]); } }
        if (P.grade && P.grade.sharpen_amp !== undefined) { var shp = fx.property("S_Sharpen"); if (shp) { shp.property("S_Sharpen-0050").setValue(P.grade.sharpen_amp); log("S_Sharpen amp = " + P.grade.sharpen_amp); } else log("S_Sharpen missing - sharpen_amp not applied"); }

        // 5. captions: one text layer per word at the measured layout position
        function textLayer(str, font, size, fill, strokeW) {
            var t = comp.layers.addText(str);
            var sp = t.property("ADBE Text Properties").property("ADBE Text Document");
            var td = sp.value;
            td.resetCharStyle(); td.font = font; td.fontSize = size; td.fillColor = fill; td.applyFill = true;
            td.tracking = 0; td.justification = ParagraphJustification.CENTER_JUSTIFY;
            if (strokeW > 0) { td.applyStroke = true; td.strokeColor = [0, 0, 0]; td.strokeWidth = strokeW; td.strokeOverFill = false; } else td.applyStroke = false;
            sp.setValue(td);
            return t;
        }
        var nW = P.words.length, widthLog = [];
        for (var w = 0; w < nW; w++) {
            var W0 = P.words[w];
            var t = textLayer(W0.t, P.cap_font, W0.em, hex(W0.c), W0.em * P.stroke_em * 2);
            t.name = "cap " + W0.ci + "." + w + " " + W0.t;
            t.inPoint = W0.a * f1; t.outPoint = (W0.e + 1) * f1;
            TG(t).property("ADBE Position").setValue([W0.x, W0.y]);
            // pop in about the word's centre: anchor at the visual centre (cap height / 2 above the baseline)
            TG(t).property("ADBE Anchor Point").setValue([0, -W0.em * P.cap_ratio / 2]);
            TG(t).property("ADBE Position").setValue([W0.x, W0.y - W0.em * P.cap_ratio / 2]);
            var a0 = W0.a * f1, a1 = Math.max(W0.f, W0.a + 3) * f1;
            TG(t).property("ADBE Scale").setValuesAtTimes([a0, a1], [[80, 80], [100, 100]]);
            TG(t).property("ADBE Opacity").setValuesAtTimes([a0, a0 + 2 * f1], [0, 100]);
            var ds = t.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
            ds.property("ADBE Drop Shadow-0001").setValue([0, 0, 0]);
            var op = ds.property("ADBE Drop Shadow-0002"); op.setValue(op.hasMax ? op.maxValue * P.shadow_alpha : 140);
            ds.property("ADBE Drop Shadow-0004").setValue(0);
            ds.property("ADBE Drop Shadow-0005").setValue(W0.em * 0.35);
            if (W0.kw) {
                var dg = t.property("ADBE Effect Parade").addProperty("PEDG2");
                dg.property(24).setValue(P.glow.radius); dg.property(25).setValue(P.glow.exposure);
            }
            if (w < 3) { var r = t.sourceRectAtTime(W0.a * f1 + 0.5, false); widthLog.push(W0.t + " ae=" + Math.round(r.width) + " pil=" + Math.round(W0.inkw)); }
        }
        log("captions: " + nW + " word layers; width check " + widthLog.join(", "));

        // 6. title card: rounded white box + text, product names purple, fully visible on frame 0
        var tt = textLayer(P.title.text, P.title.font, P.title.size, [0.05, 0.05, 0.07], 0);
        tt.name = "Title text";
        var tsp = tt.property("ADBE Text Properties").property("ADBE Text Document"), tdd = tsp.value;
        tdd.leading = P.title.size * 1.15;
        for (var h = 0; h < P.title.hl.length; h++) { var rg = P.title.hl[h]; var cr = tdd.characterRange(rg[0], rg[1]); cr.fillColor = hex(P.title.hl_color); }
        tsp.setValue(tdd);
        var rr = tt.sourceRectAtTime(0, false);
        TG(tt).property("ADBE Anchor Point").setValue([rr.left + rr.width / 2, rr.top + rr.height / 2]);
        TG(tt).property("ADBE Position").setValue([P.W / 2, P.title.top + P.title.pad_y + rr.height / 2]);
        var box = comp.layers.addShape(); box.name = "Title box";
        var grp = box.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
        var rect = grp.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Rect");
        var bw = rr.width + 2 * P.title.pad_x, bh = rr.height + 2 * P.title.pad_y;
        rect.property("ADBE Vector Rect Size").setValue([bw, bh]); rect.property("ADBE Vector Rect Roundness").setValue(28);
        var fill = grp.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill"); fill.property("ADBE Vector Fill Color").setValue([1, 1, 1]);
        TG(box).property("ADBE Position").setValue([P.W / 2, P.title.top + bh / 2]);
        var bsh = box.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
        bsh.property("ADBE Drop Shadow-0004").setValue(8); bsh.property("ADBE Drop Shadow-0005").setValue(28);
        box.moveAfter(tt);
        P.title.box = [P.W / 2 - bw / 2, P.title.top, P.W / 2 + bw / 2, P.title.top + bh];
        log("title box " + Math.round(bw) + "x" + Math.round(bh) + " top " + P.title.top + " bottom " + Math.round(P.title.top + bh) + " (layout assumed " + P.title.bottom + ")");

        // render queue: lossless chunks are set by clip_build.py render (aerender -s/-e); template here is the fallback
        var rq = proj.renderQueue.items.add(comp);
        rq.applyTemplate("Best Settings");
        rq.outputModule(1).applyTemplate("Lossless");
        rq.outputModule(1).file = new File(P.out_video.replace(/\.mp4$/, ".avi"));
        proj.save(new File(P.aep));
        log("saved " + P.aep);
        log("BUILD_OK");
    } catch (e) {
        log("BUILD_ERROR " + e.toString() + " line " + e.line);
    }
})();
