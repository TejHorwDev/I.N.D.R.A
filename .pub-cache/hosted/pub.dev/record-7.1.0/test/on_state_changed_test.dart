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

  group('onStateChanged', () {
    test('returns a stream', () {
      expect(recorder.onStateChanged(), isA<Stream<RecordState>>());
    });

    test('returns the same stream on repeated calls', () {
      final a = recorder.onStateChanged();
      final b = recorder.onStateChanged();
      expect(identical(a, b), isTrue);
    });

    test('returns the same stream after start()', () async {
      final before = recorder.onStateChanged();
      await recorder.start(const RecordConfig(), path: '/x.m4a');
      expect(identical(recorder.onStateChanged(), before), isTrue);
    });

    test('receives states emitted by the platform', () async {
      final states = <RecordState>[];
      recorder.onStateChanged().listen(states.add);
      await pump();

      fake.emitState(RecordState.record);
      await pump();
      fake.emitState(RecordState.pause);
      await pump();
      fake.emitState(RecordState.stop);
      await pump();

      expect(states, [RecordState.record, RecordState.pause, RecordState.stop]);
    });

    test('works when called before start()', () async {
      final states = <RecordState>[];
      recorder.onStateChanged().listen(states.add);
      await pump();

      await recorder.start(const RecordConfig(), path: '/x.m4a');
      fake.emitState(RecordState.record);
      await pump();

      expect(states, contains(RecordState.record));
    });

    test('multiple listeners receive the same events', () async {
      final states1 = <RecordState>[];
      final states2 = <RecordState>[];
      recorder.onStateChanged().listen(states1.add);
      recorder.onStateChanged().listen(states2.add);
      await pump();

      fake.emitState(RecordState.record);
      await pump();

      expect(states1, [RecordState.record]);
      expect(states2, [RecordState.record]);
    });

    test('forwards platform stream errors to listeners', () async {
      final errors = <Object>[];
      recorder.onStateChanged().listen((_) {}, onError: errors.add);
      await pump();

      fake.emitError(Exception('platform error'));
      await pump();

      expect(errors, hasLength(1));
      expect(errors.first, isA<Exception>());
    });

    test('drops platform stream errors when there are no listeners', () async {
      recorder.onStateChanged(); // initialises stream but no listener attached
      await pump();

      // Should not throw even though no listener is attached.
      expect(() => fake.emitError(Exception('dropped')), returnsNormally);
      await pump();
    });
  });
}
