LINE instant messenger protocol documentation
=============================================

These files are the results of research into the LINE instant messenger protocol. The purpose of the
research is to provide information about its inner workings and security to its users as well as
produce documentation required to create compatible client software implementations.

The information provided here was gathered by examining official LINE client software.

Files
-----

* **line-protocol.md:** Explanation of the wire protocol, the usage of the different functions and
  other implementation details.
* **line.thrift:** An Apache Thrift interface file produced by analyzing official LINE software.
* **line_main.thrift:** A filtered version of line.thrift with only the core services required for
  an instant messenger and some identifiers renamed for better compatibility with some programming
  languages.

*This work is not connected with LINE Corporation.*
