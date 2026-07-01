import 'dart:typed_data';

import 'package:web/web.dart' as web;
import 'dart:js_interop';

import 'encoder.dart';

class PcmEncoder implements Encoder {
  final List<Uint8List> _chunks = [];

  @override
  void encode(Int16List buffer) {
    _chunks.add(buffer.buffer.asUint8List());
  }

  @override
  web.Blob finish() {
    final blob = web.Blob(
      _chunks.map((c) => c.toJS).toList().toJS,
      web.BlobPropertyBag(type: 'audio/pcm'),
    );

    cleanup();

    return blob;
  }

  @override
  void cleanup() => _chunks.clear();
}
