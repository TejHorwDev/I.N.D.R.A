package com.llfbandit.record.record.format

import android.media.MediaFormat
import com.llfbandit.record.record.model.AudioEncoder
import com.llfbandit.record.record.model.RecordConfig
import com.llfbandit.record.record.container.IContainerWriter
import com.llfbandit.record.record.encoder.EncoderListener
import com.llfbandit.record.record.encoder.IEncoder

/**
 * Represents an audio format.
 * This class is responsible for creating the encoder and container for the specified format.
 * It also provides the [MediaFormat] for the encoded audio stream.
 */
sealed class Format {
  /**
   * The MIME type of the encoded audio stream inside the container.
   */
  abstract val mimeTypeAudio: String

  /**
   * Create a [MediaFormat] representing the encoded audio with parameters matching the specified
   * input PCM audio format.
   */
  abstract fun getMediaFormat(config: RecordConfig): MediaFormat

  internal open fun adjustSampleRate(format: MediaFormat, sampleRate: Int) {
    format.setInteger(MediaFormat.KEY_SAMPLE_RATE, sampleRate)
  }

  internal open fun adjustNumChannels(format: MediaFormat, numChannels: Int) {
    format.setInteger(MediaFormat.KEY_CHANNEL_COUNT, numChannels)
  }

  /**
   * Create a container to write the encoded data.
   *
   * @param path The output path if the container writes to file.
   */
  abstract fun createWriter(path: String?): IContainerWriter

  companion object {
    const val KEY_X_FRAME_SIZE_IN_BYTES = "x-frame-size-in-bytes"

    /**
     * Create an encoder that produces [MediaFormat] output.
     */
    fun createEncoder(
      config: RecordConfig,
      listener: EncoderListener
    ): Pair<IEncoder, MediaFormat> {
      val format = selectFormat(config)
      val mediaFormat = format.getMediaFormat(config)
      val encoder = FormatCodecSelector.findCodec(format, config, mediaFormat, listener)
      return Pair(encoder, mediaFormat)
    }

    private fun selectFormat(config: RecordConfig): Format {
      return when (config.encoder) {
        AudioEncoder.AacLc, AudioEncoder.AacEld, AudioEncoder.AacHe -> AacFormat()
        AudioEncoder.AmrNb -> AmrNbFormat()
        AudioEncoder.AmrWb -> AmrWbFormat()
        AudioEncoder.Flac -> FlacFormat()
        AudioEncoder.Pcm16bits -> PcmFormat()
        AudioEncoder.Opus -> OpusFormat()
        AudioEncoder.Wav -> WaveFormat()
      }
    }
  }
}
