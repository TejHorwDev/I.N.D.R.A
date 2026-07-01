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

  group('stop', () {
    test('calls platform stop', () async {
      await recorder.stop();
      expect(fake.calls, containsAllInOrder(['create', 'stop']));
    });

    test('returns path from platform', () async {
      fake.stopResult = '/out/recording.m4a';
      expect(await recorder.stop(), '/out/recording.m4a');
    });

    test('returns null when platform returns null', () async {
      fake.stopResult = null;
      expect(await recorder.stop(), isNull);
    });

    test('closes the byte stream after stopping', () async {
      final stream = await recorder.startStream(const RecordConfig());
      var done = false;
      stream.listen(null, onDone: () => done = true);

      await recorder.stop();
      await pump();

      expect(done, isTrue);
    });
  });
}
