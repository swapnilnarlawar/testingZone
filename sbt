object Main {
  def main(args: Array[String]): Unit = {
    println("=== OpenTelemetry Environment Variables Check ===")
    println("OTEL_EXPORTER_OTLP_ENDPOINT: " + sys.env.getOrElse("OTEL_EXPORTER_OTLP_ENDPOINT", "❌ Not set"))
    println("OTEL_EXPORTER_OTLP_HEADERS: " + sys.env.getOrElse("OTEL_EXPORTER_OTLP_HEADERS", "❌ Not set"))
    println("OTEL_RESOURCE_ATTRIBUTES: " + sys.env.getOrElse("OTEL_RESOURCE_ATTRIBUTES", "❌ Not set"))
    println("================================================")
    
    Thread.sleep(5000)
  }
}
