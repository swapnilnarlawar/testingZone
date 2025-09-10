import io.opentelemetry.api.common.Attributes
import io.opentelemetry.api.metrics.{Meter, ObservableDoubleMeasurement}
import io.opentelemetry.sdk.OpenTelemetrySdk
import io.opentelemetry.sdk.metrics.SdkMeterProvider
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter
import io.opentelemetry.sdk.resources.Resource
import io.opentelemetry.semconv.resource.attributes.ResourceAttributes
import java.util.concurrent.TimeUnit

object Main {
  def main(args: Array[String]): Unit = {

    val exporter = OtlpHttpMetricExporter.builder()
      .setEndpoint("https://otelcol.test.net/v1/metrics")
      .addHeader("X-Scope-OrgID", "234e8236-3242-1231-342")
      .build()

    val resource = Resource.getDefault.merge(
      Resource.create(
        Attributes.builder()
          .put(ResourceAttributes.SERVICE_NAME, "m922633_oteltest")
          .put("cmdbReference", "AT12345")
          .build()
      )
    )

    val metricReader = PeriodicMetricReader.builder(exporter)
      .setInterval(5000, TimeUnit.MILLISECONDS)
      .build()

    val meterProvider = SdkMeterProvider.builder()
      .setResource(resource)
      .registerMetricReader(metricReader)
      .build()

    val openTelemetry = OpenTelemetrySdk.builder()
      .setMeterProvider(meterProvider)
      .buildAndRegisterGlobal()

    val meter: Meter = openTelemetry.getMeter("manualTest")

    // Metric 1
    meter.gaugeBuilder("example_gauge_m922633")
      .setDescription("first gauge metric")
      .buildWithCallback { measurement: ObservableDoubleMeasurement =>
        measurement.record(42.5, Attributes.builder().put("environment", "dev").build())
      }

    // Metric 2
    meter.gaugeBuilder("records_processed_total")
      .setDescription("second gauge metric")
      .buildWithCallback { measurement: ObservableDoubleMeasurement =>
        measurement.record(12345.0, Attributes.builder().put("environment", "qa").build())
      }

    // Metric 3
    meter.gaugeBuilder("multi_datapoint_metric")
      .setDescription("third gauge metric")
      .buildWithCallback { measurement: ObservableDoubleMeasurement =>
        measurement.record(77.7, Attributes.builder().put("environment", "dev").build())
        measurement.record(88.8, Attributes.builder().put("environment", "qa").build())
      }

    println("✅ Registered 3 metrics with OTLP HTTP exporter")

    // Keep JVM alive to flush metrics
    Thread.sleep(20000)
  }
}
