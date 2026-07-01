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

  group('cancel', () {
    test('calls platform cancel', () async {
      await recorder.cancel();
      expect(fake.calls, containsAllInOrder(['create', 'cancel']));
    });

    test('closes the byte stream after cancelling', () async {
      final stream = await recorder.startStream(const RecordConfig());
      var done = false;
      stream.listen(null, onDone: () => done = true);

      await recorder.cancel();
      await pump();

      expect(done, isTrue);
    });
  });
}
