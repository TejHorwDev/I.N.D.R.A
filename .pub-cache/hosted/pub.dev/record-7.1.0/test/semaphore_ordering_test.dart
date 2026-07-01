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

  group('semaphore ordering', () {
    test('create completes before any subsequent call', () async {
      final stopFuture = recorder.stop();
      await stopFuture;

      final createIdx = fake.calls.indexOf('create');
      final stopIdx = fake.calls.lastIndexOf('stop');
      expect(createIdx, lessThan(stopIdx));
    });

    test('concurrent calls are serialized', () async {
      final results = await Future.wait([
        recorder.isRecording(),
        recorder.isPaused(),
        recorder.hasPermission(),
      ]);

      expect(results, hasLength(3));
      final createIdx = fake.calls.indexOf('create');
      for (final method in ['isRecording', 'isPaused', 'hasPermission']) {
        expect(fake.calls.indexOf(method), greaterThan(createIdx));
      }
    });

    test('calls complete in the order they were issued', () async {
      final f1 = recorder.stop();
      final f2 = recorder.pause();
      await Future.wait([f1, f2]);

      final stopIdx = fake.calls.indexOf('stop');
      final pauseIdx = fake.calls.indexOf('pause');
      expect(stopIdx, lessThan(pauseIdx));
    });
  });
}
