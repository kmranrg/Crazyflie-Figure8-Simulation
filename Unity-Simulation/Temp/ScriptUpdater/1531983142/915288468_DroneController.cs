using UnityEngine;
using UnityEngine.InputSystem;

public class DroneController : MonoBehaviour
{
    [Header("Drone Physics")]
    public float horizontalSpeed = 0.05f;
    public float verticalSpeed = 0.05f;
    public float yawSpeed = 50f;
    public float dampingForce = 1.0f;
    
    private Rigidbody rb;
    private bool useManualControl = true;
    private float forwardInput;
    private float lateralInput;
    private float verticalInput;
    private float yawInput;
    
    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.freezeRotation = true;
    }
    
    void FixedUpdate()
    {
        if (useManualControl)
        {
            ApplyThrustAndMovement();
        }
        else
        {
            FollowTrajectory();
        }
    }
    
    void ApplyThrustAndMovement()
    {
        float hoverForce = rb.mass * Mathf.Abs(Physics.gravity.y);
        
        Vector3 moveDirection = Vector3.zero;
        
        if (forwardInput != 0)
        {
            moveDirection += transform.forward * forwardInput;
        }
        
        if (lateralInput != 0)
        {
            moveDirection += transform.right * lateralInput;
        }
        
        moveDirection.Normalize();
        
        if (moveDirection.magnitude > 0)
        {
            rb.AddForce(moveDirection * horizontalSpeed, ForceMode.Force);
        }
        
        if (verticalInput != 0)
        {
            rb.AddForce(Vector3.up * verticalInput * verticalSpeed, ForceMode.Force);
        }
        
        rb.AddForce(Vector3.up * hoverForce, ForceMode.Force);
        
        if (yawInput != 0)
        {
            transform.Rotate(Vector3.up * yawInput * yawSpeed * Time.fixedDeltaTime);
        }
        
        rb.linearVelocity *= (1f - dampingForce * Time.fixedDeltaTime);
    }
    
    void FollowTrajectory()
    {
    }
    
    public void OnForward(InputValue value)
    {
        forwardInput = value.Get<float>();
    }
    
    public void OnLateral(InputValue value)
    {
        lateralInput = value.Get<float>();
    }
    
    public void OnVertical(InputValue value)
    {
        verticalInput = value.Get<float>();
    }
    
    public void OnYaw(InputValue value)
    {
        yawInput = value.Get<float>();
    }
    
    public void SetAutomaticControl(bool automatic)
    {
        useManualControl = !automatic;
        rb.freezeRotation = automatic;
    }
}