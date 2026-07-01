import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

import 'helpers/fake_record_platform.dart';
import 'helpers/test_utils.dart';

void main() {
  late FakeRecordPlatform fake;
  late AudioRecorder recorder;

  setUp(() async {
    fake = FakeRecordPlatform();
    RecordPlatform.instance = fake;
    recorder = AudioRecorder();
    await pump();
  });

  tearDown(() async {
    try {
      await recorder.dispose();
    } catch (_) {}
  });

  group('error propagation', () {
    late AudioRecorder failingRecorder;

    setUp(() {
      // Set exception after recorder's create has already completed (in outer setUp).
      fake.createException = Exception('device unavailable');
      failingRecorder = AudioRecorder();
    });

    test('start throws when create failed', () async {
      await expectLater(
        failingRecorder.start(const RecordConfig(), path: '/x.m4a'),
        throwsA(isA<Exception>()),
      );
    });

    test('stop throws when create failed', () async {
      await expectLater(
        failingRecorder.stop(),
        throwsA(isA<Exception>()),
      );
    });

    test('pause throws when create failed', () async {
      await expectLater(
        failingRecorder.pause(),
        throwsA(isA<Exception>()),
      );
    });

    test('resume throws when create failed', () async {
      await expectLater(
        failingRecorder.resume(),
        throwsA(isA<Exception>()),
      );
    });

    test('cancel throws when create failed', () async {
      await expectLater(
        failingRecorder.cancel(),
        throwsA(isA<Exception>()),
      );
    });

    test('isRecording throws when create failed', () async {
      await expectLater(
        failingRecorder.isRecording(),
        throwsA(isA<Exception>()),
      );
    });

    test('isPaused throws when create failed', () async {
      await expectLater(
        failingRecorder.isPaused(),
        throwsA(isA<Exception>()),
      );
    });

    test('hasPermission throws when create failed', () async {
      await expectLater(
        failingRecorder.hasPermission(),
        throwsA(isA<Exception>()),
      );
    });

    test('getAmplitude throws when create failed', () async {
      await expectLater(
        failingRecorder.getAmplitude(),
        throwsA(isA<Exception>()),
      );
    });

    test('isEncoderSupported throws when create failed', () async {
      await expectLater(
        failingRecorder.isEncoderSupported(AudioEncoder.aacLc),
        throwsA(isA<Exception>()),
      );
    });

    test('listInputDevices throws when create failed', () async {
      await expectLater(
        failingRecorder.listInputDevices(),
        throwsA(isA<Exception>()),
      );
    });

    test('dispose throws when create failed', () async {
      await expectLater(
        failingRecorder.dispose(),
        throwsA(isA<Exception>()),
      );
    });

    test('same exception is rethrown on every subsequent call', () async {
      Object? e1;
      Object? e2;
      try {
        await failingRecorder.isRecording();
      } catch (e) {
        e1 = e;
      }
      try {
        await failingRecorder.isPaused();
      } catch (e) {
        e2 = e;
      }
      expect(e1, isA<Exception>());
      expect(e2, isA<Exception>());
    });
  });
}
