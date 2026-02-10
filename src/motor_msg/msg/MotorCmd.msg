# MotorCmd.msg

# uint8 mode;  //Mode（Foc mode -> 0x01 ，stop mode -> 0x00)
float32 q     #Target position (rad)
# float dq;    //Target velocity (rad/s)
# float tau;   //Target torque (N.M)
float32 kp
float32 kd
# unsigned long reserve[3]; 
