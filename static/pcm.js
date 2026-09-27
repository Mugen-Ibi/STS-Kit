// Direct PCM16 decoding avoids the browser's general-purpose codec pipeline.
(function (root) {
  function decodePcm16(context, buffer) {
    const v = new DataView(buffer);
    const tag = (i) => String.fromCharCode(...new Uint8Array(buffer, i, 4));
    if (v.byteLength < 44 || tag(0) !== 'RIFF' || tag(8) !== 'WAVE') return null;
    let channels, rate, dataOffset, dataSize;
    for (let p = 12; p + 8 <= v.byteLength;) {
      const size = v.getUint32(p + 4, true), start = p + 8;
      if (start + size > v.byteLength) return null;
      if (tag(p) === 'fmt ') {
        if (size < 16 || v.getUint16(start, true) !== 1 || v.getUint16(start + 14, true) !== 16) return null;
        channels = v.getUint16(start + 2, true); rate = v.getUint32(start + 4, true);
      }
      if (tag(p) === 'data') { dataOffset = start; dataSize = size; }
      p = start + size + (size % 2);
    }
    if (![1, 2].includes(channels) || rate < 8000 || rate > 96000 || !dataSize || dataSize % (2 * channels)) return null;
    const frames = dataSize / (2 * channels), audio = context.createBuffer(channels, frames, rate);
    for (let c = 0; c < channels; c++) {
      const target = audio.getChannelData(c);
      for (let i = 0; i < frames; i++) target[i] = v.getInt16(dataOffset + (i * channels + c) * 2, true) / 32768;
    }
    return audio;
  }
  root.STSAudio = {decodePcm16};
  if (typeof module !== 'undefined') module.exports = root.STSAudio;
})(globalThis);
