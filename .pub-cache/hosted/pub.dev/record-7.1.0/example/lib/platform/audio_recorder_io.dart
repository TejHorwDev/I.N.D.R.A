// ignore_for_file: avoid_print

import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import 'audio_encoder_ext.dart';

mixin AudioRecorderMixin {
  Future<void> recordFile(AudioRecorder recorder, RecordConfig config) async {
    final path = await _getPath(config.encoder);

    await recorder.start(config, path: path);
  }

  Future<void> recordStream(
    AudioRecorder recorder,
    RecordConfig config, {
    void Function(String path)? onStop,
  }) async {
    final path = await _getPath(config.encoder);

    final file = File(path);

    final stream = await recorder.startStream(config);

    stream.listen(
      (data) {
        file.writeAsBytesSync(data, mode: FileMode.append);
      },
      onDone: () {
        print('End of stream. File written to $path.');
        onStop?.call(path);
      },
    );
  }

  void downloadWebData(String path, AudioEncoder encoder) {}

  Future<String> _getPath(AudioEncoder encoder) async {
    final dir = await getApplicationDocumentsDirectory();
    return p.join(
      dir.path,
      'audio_${DateTime.now().millisecondsSinceEpoch}.${encoder.fileExtension}',
    );
  }
}
