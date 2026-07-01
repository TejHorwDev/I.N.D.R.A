import 'dart:async';

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

  group('dispose', () {
    test('calls platform dispose', () async {
      await recorder.dispose();
      expect(fake.calls, containsAllInOrder(['create', 'dispose']));
    });

    test('closes the state stream', () async {
      final done = Completer<void>();
      recorder.onStateChanged().listen(null, onDone: done.complete);
      await pump();

      await recorder.dispose();
      await pump();

      expect(done.isCompleted, isTrue);
    });

    test('closes the byte stream if recording was active', () async {
      final stream = await recorder.startStream(const RecordConfig());
      var done = false;
      stream.listen(null, onDone: () => done = true);

      await recorder.dispose();
      await pump();

      expect(done, isTrue);
    });
  });
}
