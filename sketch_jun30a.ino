
int isEnabledFlag = 0;

void setup() {
  pinMode(13, OUTPUT);     // initialize digital pin 13 as an output.
  Serial.begin(9600);     // initialize serial communication at 9600 bits per second:
}

void loop() {
  
  // read the input on analog pin 0:
  int sensorValue = analogRead(A0);
    
  if ((sensorValue < 800) && (isEnabledFlag == 0)) {
    digitalWrite(13, HIGH);   // turn the LED on (HIGH is the voltage level)
    Serial.println(sensorValue); // print out the value you read
  } else if ((sensorValue >= 800) && (isEnabledFlag == 1)) {
    digitalWrite(13, LOW);    // turn the LED off by making the voltage LOW
    Serial.println(sensorValue); // print out the value you read
  }
  
  delay(1000);              // wait for a second
}
