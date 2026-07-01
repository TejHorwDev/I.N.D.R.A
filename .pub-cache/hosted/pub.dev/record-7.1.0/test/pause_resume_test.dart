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

  group('pause', () {
    test('calls platform pause', () async {
      await recorder.pause();
      expect(fake.calls, containsAllInOrder(['create', 'pause']));
    });
  });

  group('resume', () {
    test('calls platform resume', () async {
      await recorder.resume();
      expect(fake.calls, containsAllInOrder(['create', 'resume']));
    });
  });
}
