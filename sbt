// ==============================
// UC-Compatible OpenTelemetry Metrics Test
// ==============================

try {
  // -----------------------------
  // Imports
  // -----------------------------
  import io.opentelemetry.api.metrics.{Meter, ObservableDoubleMeasurement}
  import io.opentelemetry.api.common.Attributes
  import io.opentelemetry.sdk.OpenTelemetrySdk
  import io.opentelemetry.sdk.metrics.SdkMeterProvider
  import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader
  import io.opentelemetry.sdk.resources.Resource
  import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter
  import io.opentelemetry.semconv.resource.attributes.ResourceAttributes

  println("✅ OpenTelemetry classes imported successfully!")

  // -----------------------------
  // Resource with cmdbReference
  // -----------------------------
  val resource = Resource.getDefault.merge(
    Resource.create(
      Attributes.builder()
        .put(ResourceAttributes.SERVICE_NAME, "databricks-otel-test")
        .put("cmdbReference", "AT12345") // Resource-level attribute
        .build()
    )
  )

  // -----------------------------
  // OTLP HTTP Exporter configuration
  // -----------------------------
  val exporterBuilder = OtlpHttpMetricExporter.builder()
    .setEndpoint(sys.env.getOrElse(
      "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
      throw new IllegalArgumentException("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT not set")
    ))

  sys.env.get("OTEL_EXPORTER_OTLP_HEADERS").foreach { headersStr =>
    headersStr.split(",").foreach { kv =>
      kv.split("=", 2) match {
        case Array(k, v) => exporterBuilder.addHeader(k.trim, v.trim)
        case _ => println(s"⚠️ Skipping malformed header: $kv")
      }
    }
  }

  val exporter = exporterBuilder.build()

  // -----------------------------
  // MeterProvider with periodic export
  // -----------------------------
  val metricReader = PeriodicMetricReader.builder(exporter)
    .setInterval(5000, java.util.concurrent.TimeUnit.MILLISECONDS)
    .build()

  val meterProvider = SdkMeterProvider.builder()
    .setResource(resource)
    .registerMetricReader(metricReader)
    .build()

  val openTelemetry = OpenTelemetrySdk.builder()
    .setMeterProvider(meterProvider)
    .buildAndRegisterGlobal()

  val meter: Meter = openTelemetry.getMeter("manualTest")

  // ==============================
  // Metric 1: Single datapoint
  // ==============================
  meter.gaugeBuilder("first_gauge_m922633")
    .setDescription("First gauge metric")
    .buildWithCallback { measurement: ObservableDoubleMeasurement =>
      measurement.record(42.5, Attributes.builder().put("environment", "dev").put("cmdbReference", "AT12345").build())
    }

  // ==============================
  // Metric 2: Single datapoint
  // ==============================
  meter.gaugeBuilder("records_processed_total")
    .setDescription("Second gauge metric")
    .buildWithCallback { measurement: ObservableDoubleMeasurement =>
      measurement.record(12345.0, Attributes.builder().put("environment", "qa").put("cmdbReference", "AT12345").build())
    }

  // ==============================
  // Metric 3: Multiple datapoints
  // ==============================
  meter.gaugeBuilder("multi_datapoint_metric")
    .setDescription("Third gauge metric")
    .buildWithCallback { measurement: ObservableDoubleMeasurement =>
      measurement.record(77.7, Attributes.builder().put("environment", "dev").put("cmdbReference", "AT12345").build())
      measurement.record(88.8, Attributes.builder().put("environment", "qa").put("cmdbReference", "AT12345").build())
    }

  println("✅ Metrics registered successfully. Exporting via OTLP...")

  // ==============================
  // Keep notebook driver alive for export
  // ==============================
  Thread.sleep(20000) // 20 seconds; adjust as needed for testing

} catch {
  case e: Throwable =>
    println("❌ Error during OpenTelemetry setup:")
    println(e.getMessage)
    e.printStackTrace()
}
