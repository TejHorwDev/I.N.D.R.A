/// Drains the microtask and event queues to let async chains resolve.
Future<void> pump({int count = 10}) async {
  for (var i = 0; i < count; i++) {
    await Future<void>.value();
  }
}
