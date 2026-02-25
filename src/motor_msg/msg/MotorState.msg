# MotorState.msg

# uint8 mode           # Mode, 0x01 for control
float32 q            # Joint angle
float32 dq           # Joint velocity
# float32 ddq          # Joint acceleration
float32 tau_est      # Estimated torque
# float32 q_raw        # raw data of q
# float32 dq_raw       # raw data of dq
# float32 ddq_raw      # raw data of ddq
# int8 temperature
# uint32 lost
# uint32[2] reserve
