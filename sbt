name := "otel-demo"
version := "0.1"
scalaVersion := "2.12.17"

libraryDependencies ++= Seq(
  "io.opentelemetry" % "opentelemetry-api" % "1.53.0",
  "io.opentelemetry" % "opentelemetry-sdk" % "1.53.0",
  "io.opentelemetry" % "opentelemetry-exporter-otlp" % "1.53.0",
  "io.opentelemetry" % "opentelemetry-semconv" % "1.34.0",
  "io.opentelemetry" % "opentelemetry-sdk-extension-resources" % "1.19.0"
)



object Main {
  def main(args: Array[String]): Unit = {
    println("Hello, OpenTelemetry Scala!")
  }
}
