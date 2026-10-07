// bundle สำหรับพรีวิวใน editor (esbuild → scripts/editor/player.js) — ใช้ component ตัวเดียวกับตอนเรนเดอร์
import React from 'react';
import {createRoot} from 'react-dom/client';
import {Player} from '@remotion/player';
import {Explainer} from './Explainer.jsx';

window.ClipcutPlayer = {
  mount(el, props, {fps = 30, onReady} = {}) {
    const ref = React.createRef();
    const root = createRoot(el);
    let cur = props;
    const render = () => root.render(
      <Player ref={ref} component={Explainer} inputProps={cur} durationInFrames={Math.max(1, cur.total || 1)} fps={fps}
        compositionWidth={1080} compositionHeight={1920} style={{width: '100%', height: '100%'}} controls={false} clickToPlay={false} />
    );
    render();
    const api = {
      setProps(p) { cur = p; render(); },
      seek(f) { ref.current && ref.current.seekTo(Math.round(f)); },
      play() { ref.current && ref.current.play(); },
      pause() { ref.current && ref.current.pause(); },
      frame() { return ref.current ? ref.current.getCurrentFrame() : 0; },
    };
    setTimeout(() => onReady && onReady(api), 0);
    return api;
  },
};
