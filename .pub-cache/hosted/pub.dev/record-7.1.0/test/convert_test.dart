import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

import 'helpers/fake_record_platform.dart';
import 'helpers/test_utils.dart';

void main() {
  late AudioRecorder recorder;

  setUp(() async {
    RecordPlatform.instance = FakeRecordPlatform();
    recorder = AudioRecorder();
    await pump();
  });

  tearDown(() async {
    try {
      await recorder.dispose();
    } catch (_) {}
  });

  group('ConvertExt.convertBytesToInt16', () {
    test('converts little-endian bytes by default', () {
      // 0x0100 = 256 in little-endian, 0xFF7F = 32767 in little-endian
      final bytes = Uint8List.fromList([0x00, 0x01, 0xFF, 0x7F]);
      expect(recorder.convertBytesToInt16(bytes), equals([256, 32767]));
    });

    test('converts big-endian bytes when specified', () {
      // 0x0100 = 256 in big-endian, 0x7FFF = 32767 in big-endian
      final bytes = Uint8List.fromList([0x01, 0x00, 0x7F, 0xFF]);
      expect(
        recorder.convertBytesToInt16(bytes, Endian.big),
        equals([256, 32767]),
      );
    });

    test('handles negative values', () {
      // 0x0080 little-endian = -32768, 0xFFFF little-endian = -1
      final bytes = Uint8List.fromList([0x00, 0x80, 0xFF, 0xFF]);
      expect(recorder.convertBytesToInt16(bytes), equals([-32768, -1]));
    });

    test('returns empty list for empty input', () {
      expect(recorder.convertBytesToInt16(Uint8List(0)), isEmpty);
    });

    test('converts a single sample', () {
      final bytes = Uint8List.fromList([0x00, 0x00]);
      expect(recorder.convertBytesToInt16(bytes), equals([0]));
    });

    test('throws ArgumentError for odd-length input', () {
      final bytes = Uint8List.fromList([0x01, 0x02, 0x03]);
      expect(
        () => recorder.convertBytesToInt16(bytes),
        throwsA(
          isA<ArgumentError>().having(
            (e) => e.message,
            'message',
            'Input byte length must be even.',
          ),
        ),
      );
    });

    test('output length is half of input length', () {
      final bytes = Uint8List(8);
      expect(recorder.convertBytesToInt16(bytes).length, equals(4));
    });
  });
}
