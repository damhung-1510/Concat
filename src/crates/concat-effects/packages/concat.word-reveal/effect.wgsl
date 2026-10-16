struct Params { progress: f32 }

// Each word of a title carries its place in reading order, 0 for the first and
// 1 for the last (see `reveal_order`). A word shows once Progress has reached its
// place, fading in over a short run of Progress so it arrives rather than blinks.
// Off a title the order is 0 everywhere, so only Progress at its very lowest hides
// anything; at its default of 100 the whole picture passes as it came.
const SOFT: f32 = 0.05;

// A word's box is the line the layout gave it, so the ink of a tone mark above it or a
// tail below it can fall just outside, where the map reads 0 ("revealed from the start")
// and would show as specks before its word. Taking the latest order within a few pixels
// gives that ink its word's turn. (About 7px up and down and 4px across at 1080x1920: any more holds back a descender,
// the next line being that near.)
fn order_near(uv: vec2<f32>) -> f32 {
    var o = 0.0;
    for (var i = -1; i <= 1; i = i + 1) {
        for (var j = -1; j <= 1; j = j + 1) {
            o = max(o, reveal_order(uv + vec2<f32>(f32(i) * 0.004, f32(j) * 0.0035)));
        }
    }
    return o;
}

fn effect(uv: vec2<f32>) -> vec4<f32> {
    let c = sample(uv);
    // Progress 100 is "every word, fully in", so the scale runs a little past 1.
    let p = params.progress / 100.0 * (1.0 + SOFT);
    let shown = smoothstep(0.0, SOFT, p - order_near(uv));
    return vec4<f32>(c.rgb, c.a * shown);
}
