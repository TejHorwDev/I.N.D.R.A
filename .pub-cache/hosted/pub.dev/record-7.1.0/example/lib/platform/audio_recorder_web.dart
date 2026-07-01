import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

import 'package:record/record.dart';

import 'audio_encoder_ext.dart';

mixin AudioRecorderMixin {
  Future<void> recordFile(AudioRecorder recorder, RecordConfig config) {
    return recorder.start(config, path: '');
  }

  Future<void> recordStream(
    AudioRecorder recorder,
    RecordConfig config, {
    void Function(String path)? onStop,
  }) async {
    final bytes = <int>[];
    final stream = await recorder.startStream(config);

    stream.listen(
      (data) => bytes.addAll(data),
      onDone: () {
        final url = web.URL.createObjectURL(
          web.Blob(<JSUint8Array>[Uint8List.fromList(bytes).toJS].toJS),
        );
        downloadWebData(url, config.encoder);
        onStop?.call(url);
      },
    );
  }

  void downloadWebData(String path, AudioEncoder encoder) {
    final anchor = web.document.createElement('a') as web.HTMLAnchorElement
      ..href = path
      ..style.display = 'none'
      ..download = 'audio.${encoder.fileExtension}';
    web.document.body!.appendChild(anchor);
    anchor.click();
    web.document.body!.removeChild(anchor);
  }
}
