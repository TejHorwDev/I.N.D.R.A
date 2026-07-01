import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'encoder.dart';

// Assumes bit depth to int16
class WavEncoder implements Encoder {
  final int sampleRate;
  final int numChannels;
  final List<Uint8List> _chunks = [];
  int _audioDataLength = 0;

  WavEncoder({required this.sampleRate, required this.numChannels});

  @override
  void encode(Int16List buffer) {
    final chunk = buffer.buffer.asUint8List();
    _chunks.add(chunk);
    _audioDataLength += chunk.length;
  }

  @override
  web.Blob finish() {
    const headerSize = 44;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample ~/ 8;
    final byteRate = sampleRate * numChannels * bytesPerSample;
    final blockAlign = numChannels * bytesPerSample;

    final view = ByteData(headerSize);

    // RIFF chunk
    view.setString(0, 'RIFF');
    view.setUint32(4, headerSize + _audioDataLength - 8, Endian.little);
    view.setString(8, 'WAVE');

    view.setString(12, 'fmt ');
    view.setUint32(16, 16, Endian.little);
    view.setUint16(20, 1, Endian.little);
    view.setUint16(22, numChannels, Endian.little);
    view.setUint32(24, sampleRate, Endian.little);
    view.setUint32(28, byteRate, Endian.little);
    view.setUint16(32, blockAlign, Endian.little);
    view.setUint16(34, bitsPerSample, Endian.little);

    view.setString(36, 'data');
    view.setUint32(40, _audioDataLength, Endian.little);

    final blob = web.Blob(
      <JSUint8Array>[
        view.buffer.asUint8List().toJS,
        ..._chunks.map((c) => c.toJS),
      ].toJS,
      web.BlobPropertyBag(type: 'audio/wav'),
    );

    cleanup();

    return blob;
  }

  @override
  void cleanup() {
    _chunks.clear();
    _audioDataLength = 0;
  }
}

extension ByteDataExt on ByteData {
  void setString(int offset, String str) {
    final len = str.length;

    for (var i = 0; i < len; ++i) {
      setUint8(offset + i, str.codeUnitAt(i));
    }
  }
}
