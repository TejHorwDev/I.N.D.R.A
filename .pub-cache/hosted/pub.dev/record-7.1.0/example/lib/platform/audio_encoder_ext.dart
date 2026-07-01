import 'package:record/record.dart';

extension AudioEncoderExt on AudioEncoder {
  String get fileExtension => switch (this) {
    AudioEncoder.aacLc || AudioEncoder.aacEld || AudioEncoder.aacHe => 'm4a',
    AudioEncoder.amrNb || AudioEncoder.amrWb => '3gp',
    AudioEncoder.opus => 'opus',
    AudioEncoder.flac => 'flac',
    AudioEncoder.wav => 'wav',
    AudioEncoder.pcm16bits => 'pcm',
  };
}
