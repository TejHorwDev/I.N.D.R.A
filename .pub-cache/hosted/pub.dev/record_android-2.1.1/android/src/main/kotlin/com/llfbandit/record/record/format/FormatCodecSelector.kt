package com.llfbandit.record.record.format

import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.util.Range
import com.llfbandit.record.record.model.RecordConfig
import com.llfbandit.record.record.util.DeviceUtils
import com.llfbandit.record.record.encoder.EncoderListener
import com.llfbandit.record.record.encoder.IEncoder
import com.llfbandit.record.record.encoder.MediaCodecEncoder
import com.llfbandit.record.record.encoder.PassthroughEncoder

internal object FormatCodecSelector {
  fun findCodec(
    format: Format,
    config: RecordConfig,
    mediaFormat: MediaFormat,
    listener: EncoderListener
  ): IEncoder {
    if (format.mimeTypeAudio == MediaFormat.MIMETYPE_AUDIO_RAW) {
      adjustToDeviceCapabilities(format, config, mediaFormat)
      syncConfig(config, mediaFormat)
      return PassthroughEncoder(config, format, mediaFormat, listener)
    }

    val codecs = MediaCodecList(MediaCodecList.REGULAR_CODECS)

    for (info in codecs.codecInfos) {
      if (!info.isEncoder) continue

      try {
        val caps = info.getCapabilitiesForType(format.mimeTypeAudio)
        if (caps != null && adjustToCapabilities(format, caps, config, mediaFormat)) {
          return MediaCodecEncoder(config, format, mediaFormat, listener, info.name)
        }
      } catch (_: IllegalArgumentException) {
        // type not supported by this codec
      }
    }

    throw Exception("No codec found for given config $mediaFormat. You should try with other values.")
  }

  /**
   * Attempts to adjust [mediaFormat] to fit within device and codec [caps].
   * On success, [config] is updated to reflect the adjusted values.
   * Returns true if the format is supported after adjustment.
   */
  private fun adjustToCapabilities(
    format: Format,
    caps: MediaCodecInfo.CodecCapabilities,
    config: RecordConfig,
    mediaFormat: MediaFormat
  ): Boolean {
    adjustToDeviceCapabilities(format, config, mediaFormat)

    var supported = caps.isFormatSupported(mediaFormat)

    if (!supported) {
      val audioCapabilities = caps.audioCapabilities

      if (audioCapabilities != null) {
        mediaFormat.setInteger(
          MediaFormat.KEY_BIT_RATE,
          checkBounds(audioCapabilities.bitrateRange, config.bitRate)
        )
        if (audioCapabilities.supportedSampleRates != null) {
          format.adjustSampleRate(
            mediaFormat,
            nearestValue(
              audioCapabilities.supportedSampleRates,
              mediaFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            )
          )
        }
        format.adjustNumChannels(
          mediaFormat,
          checkBounds(
            Range(1, audioCapabilities.maxInputChannelCount),
            mediaFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
          )
        )
      }

      supported = caps.isFormatSupported(mediaFormat)
    }

    if (supported) {
      syncConfig(config, mediaFormat)
    }

    return supported
  }

  private fun adjustToDeviceCapabilities(
    format: Format,
    config: RecordConfig,
    mediaFormat: MediaFormat
  ) {
    val device = config.device ?: DeviceUtils.getDefaultInputDevice()

    device?.let {
      // PCMReader only supports mono or stereo; ignore any device channel counts above 2.
      val deviceChannelCounts = it.channelCounts.filter { c -> c <= 2 }.toIntArray()
      if (deviceChannelCounts.isNotEmpty()) {
        val adjustedChannels = nearestValue(deviceChannelCounts, config.numChannels)
        format.adjustNumChannels(mediaFormat, adjustedChannels)
        config.numChannels = adjustedChannels
      }
    }
  }

  private fun syncConfig(config: RecordConfig, mediaFormat: MediaFormat) {
    config.sampleRate = mediaFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
    config.numChannels = mediaFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
    if (mediaFormat.containsKey(MediaFormat.KEY_BIT_RATE)) {
      config.bitRate = mediaFormat.getInteger(MediaFormat.KEY_BIT_RATE)
    }
  }

  private fun checkBounds(range: Range<Int>, value: Int): Int {
    if (range.lower > value) return range.lower
    if (range.upper < value) return range.upper
    return value
  }
}
