/* WTK1 link transport. No credentials or long-lived card token enter the sound. */
(function (root) {
  'use strict';
  function crc(bytes) {
    let value = 0xffffffff;
    for (const byte of bytes) {
      value ^= byte;
      for (let i = 0; i < 8; i++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
    }
    return (value ^ 0xffffffff) >>> 0;
  }
  function encode(link) {
    const data = new TextEncoder().encode(link);
    if (!data.length || data.length > 384) throw new Error('Setup link is too long');
    const count = Math.ceil(data.length / 32), tones = [];
    const bit = b => { tones.push(b, 1 - b); };
    for (let index = 0; index < count; index++) {
      const frame = new Uint8Array(44), view = new DataView(frame.buffer);
      view.setUint32(0, crc(data)); view.setUint16(4, data.length); frame[6] = index; frame[7] = count;
      frame.set(data.subarray(index * 32, (index + 1) * 32), 8);
      view.setUint32(40, crc(frame.subarray(0, 40)));
      for (let i = 0; i < 16; i++) tones.push(i & 1);
      for (let i = 31; i >= 0; i--) bit((0xd391c5a7 >>> i) & 1);
      for (const byte of frame) for (let i = 7; i >= 0; i--) bit((byte >>> i) & 1);
      for (let i = 0; i < 24; i++) tones.push(2);
    }
    const pcm = new Float32Array(tones.length * 144);
    tones.forEach((tone, index) => {
      if (tone === 2) return;
      const frequency = tone ? 4000 : 2000;
      for (let n = 0; n < 144; n++) pcm[index * 144 + n] = .46 * Math.sin(2 * Math.PI * frequency * n / 48000);
    });
    return pcm;
  }
  root.TaksWatchAudio = {encode};
  if (typeof module !== 'undefined') module.exports = {encode};
  if (typeof document === 'undefined') return;
  const play = document.getElementById('watch_audio_play'), stop = document.getElementById('watch_audio_stop');
  const status = document.getElementById('watch_audio_status');
  if (!play) return;
  let context, source, generation = 0;
  function halt() { generation++; if (source) { source.onended = null; source.stop(); source = null; } play.disabled = false; }
  stop.addEventListener('click', () => { halt(); status.textContent = play.dataset.stopped; });
  play.addEventListener('click', async () => {
    halt(); const run = generation; play.disabled = true;
    try {
      // Create/resume in the user gesture, before the network await (mobile autoplay policy).
      context = context || new (window.AudioContext || window.webkitAudioContext)();
      await context.resume();
      const response = await fetch(play.dataset.endpoint, {method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
      if (!response.ok) throw new Error('Setup unavailable (' + response.status + ')');
      const setup = await response.json();
      if (run !== generation) return;
      const pcm = encode(setup.url), buffer = context.createBuffer(1, pcm.length, 48000);
      buffer.copyToChannel(pcm, 0);
      source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination);
      source.onended = () => { source = null; play.disabled = false; status.textContent = play.dataset.finished; };
      source.start(); status.textContent = play.dataset.playing;
    } catch (_) { if (run === generation) { halt(); status.textContent = play.dataset.failed; } }
  });
  document.getElementById('watch_audio_reset').addEventListener('click', async event => {
    const button = event.currentTarget;
    if (!window.confirm(button.dataset.confirm)) return;
    halt(); button.disabled = true;
    try {
      const response = await fetch(button.dataset.endpoint, {method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
      if (!response.ok) throw new Error();
      status.textContent = button.dataset.confirm.startsWith('Å') ? 'Klockinloggningar återkallade.' : 'Watch logins revoked.';
    } catch (_) { status.textContent = play.dataset.failed; }
    finally { button.disabled = false; }
  });
  let qrObjectUrl;
  document.getElementById('watch_voice_qr').addEventListener('click',async event=>{
    const button=event.currentTarget;button.disabled=true;
    try {
      const response=await fetch(button.dataset.endpoint,{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error'});
      if(!response.ok)throw new Error();
      if(qrObjectUrl)URL.revokeObjectURL(qrObjectUrl);
      qrObjectUrl=URL.createObjectURL(await response.blob());
      const image=document.getElementById('watch_voice_qr_image');image.src=qrObjectUrl;image.hidden=false;
      status.textContent='Setup QR valid for 3 minutes. A fresh QR replaces the displayed one.';
      setTimeout(()=>{if(image.src===qrObjectUrl)image.hidden=true;},180000);
    }catch(_){status.textContent=play.dataset.failed;}finally{button.disabled=false;}
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) halt(); });
  window.addEventListener('pagehide', halt);
})(typeof window !== 'undefined' ? window : globalThis);
