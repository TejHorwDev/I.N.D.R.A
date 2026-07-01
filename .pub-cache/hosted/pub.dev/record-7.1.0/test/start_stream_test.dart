import 'dart:typed_data';

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

  group('startStream', () {
    test('calls platform startStream', () async {
      await recorder.startStream(const RecordConfig());
      expect(fake.calls, containsAllInOrder(['create', 'startStream']));
    });

    test('returns a stream', () async {
      final stream = await recorder.startStream(const RecordConfig());
      expect(stream, isA<Stream<Uint8List>>());
    });

    test('forwards bytes from platform stream', () async {
      final stream = await recorder.startStream(const RecordConfig());
      final received = <Uint8List>[];
      final sub = stream.listen(received.add);
      addTearDown(sub.cancel);

      final chunk = Uint8List.fromList([1, 2, 3]);
      fake.byteStreamCtrl!.add(chunk);
      await pump();

      expect(received, [chunk]);
    });

    test('forwards errors from platform stream', () async {
      final stream = await recorder.startStream(const RecordConfig());
      Object? caughtError;
      final sub = stream.listen(
        (_) {},
        onError: (Object e) => caughtError = e,
      );
      addTearDown(sub.cancel);

      fake.byteStreamCtrl!.addError(Exception('platform error'));
      await pump();

      expect(caughtError, isA<Exception>());
    });

    test('closes previous stream before starting a new one', () async {
      final stream1 = await recorder.startStream(const RecordConfig());
      var stream1Done = false;
      stream1.listen(null, onDone: () => stream1Done = true);

      await recorder.startStream(const RecordConfig());
      await pump();

      expect(stream1Done, isTrue);
    });

    test('initialises state stream before platform call', () async {
      await recorder.startStream(const RecordConfig());
      await pump();
      expect(fake.calls, contains('onStateChanged'));
    });
  });
}
