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

  group('initialization', () {
    test('create is called on construction', () {
      expect(fake.calls, contains('create'));
    });

    test('two instances call create independently', () async {
      final recorder2 = AudioRecorder();
      await pump();
      expect(fake.calls.where((c) => c == 'create'), hasLength(2));
      await recorder2.dispose();
    });

    test('different instances use distinct recorder IDs', () async {
      final recorderCreatedId = fake.lastCreatedId;
      expect(recorderCreatedId, isNotNull);
      final recorder2 = AudioRecorder();
      await pump();

      expect(fake.lastCreatedId, isNotNull);
      expect(fake.lastCreatedId, isNot(recorderCreatedId));

      await recorder2.dispose();
    });
  });
}
