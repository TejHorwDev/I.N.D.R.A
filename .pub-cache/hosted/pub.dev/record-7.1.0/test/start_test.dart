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

  group('start', () {
    test('calls platform start', () async {
      await recorder.start(const RecordConfig(), path: '/test.m4a');
      expect(fake.calls, containsAllInOrder(['create', 'start']));
    });

    test('passes path to platform', () async {
      const path = '/recordings/audio.m4a';
      await recorder.start(const RecordConfig(), path: path);
      expect(fake.lastStartPath, path);
    });

    test('initialises state stream before platform call', () async {
      await recorder.start(const RecordConfig(), path: '/x.m4a');
      await pump();
      expect(fake.calls, contains('onStateChanged'));
    });

    test('returns normally on success', () async {
      await expectLater(
        recorder.start(const RecordConfig(), path: '/ok.m4a'),
        completes,
      );
    });
  });
}
