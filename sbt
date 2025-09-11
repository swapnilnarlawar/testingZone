// ==============================
// Verify OpenTelemetry JARs
// ==============================

try {
  // Check basic OpenTelemetry API classes
  import io.opentelemetry.api.metrics.Meter
  import io.opentelemetry.api.common.Attributes

  // Check SDK classes
  import io.opentelemetry.sdk.OpenTelemetrySdk
  import io.opentelemetry.sdk.metrics.SdkMeterProvider
  import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader
  import io.opentelemetry.sdk.resources.Resource

  // Check exporter class
  import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter

  // Check semantic conventions
  import io.opentelemetry.semconv.resource.attributes.ResourceAttributes

  // Try instantiating a basic object from each JAR
  val resource = Resource.getDefault
  val meterProvider = SdkMeterProvider.builder().setResource(resource).build()
  val exporter = OtlpHttpMetricExporter.builder().setEndpoint("http://localhost:4318/v1/metrics").build()

  println("✅ All required OpenTelemetry classes are available on this cluster!")
} catch {
  case e: Throwable =>
    println("❌ Some OpenTelemetry classes are NOT available:")
    println(e.getMessage)
    e.printStackTrace()
}

// ==============================
// Verify OpenTelemetry JARs in classpath
// ==============================
val cp = sys.props("java.class.path").split(":")

// Filter only OpenTelemetry JARs
val otelJars = cp.filter(path => path.toLowerCase.contains("opentelemetry"))

if (otelJars.nonEmpty) {
  println("✅ OpenTelemetry JARs available in classpath:")
  otelJars.foreach(println)
} else {
  println("❌ No OpenTelemetry JARs found in classpath!")
}
