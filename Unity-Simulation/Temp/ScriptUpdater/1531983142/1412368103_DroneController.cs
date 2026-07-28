using UnityEngine;
using UnityEngine.InputSystem;

public class DroneController : MonoBehaviour
{
    [Header("Drone Physics")]
    public float maxThrust = 0.5f;
    public float tiltSpeed = 5f;
    public float maxTiltAngle = 30f;
    public float yawSpeed = 100f;
    
    [Header("Stabilization")]
    public float stabilizationForce = 10f;
    public float dampingForce = 2f;
    
    private Rigidbody rb;
    private bool useManualControl = true;
    private Vector2 moveInput;
    private Vector2 lateralInput;
    private float verticalInput;
    private float yawInput;
    
    void Start()
    {
        rb = GetComponent<Rigidbody>();
        rb.freezeRotation = true;
    }
    
    void Update()
    {
        if (useManualControl)
        {
            ApplyInput();
        }
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
    
    void ApplyInput()
    {
        Vector3 tilt = new Vector3(-moveInput.y, 0f, lateralInput.x) * tiltSpeed * Time.fixedDeltaTime;
        transform.Rotate(tilt);
        transform.Rotate(Vector3.up * yawInput * yawSpeed * Time.fixedDeltaTime);
        
        Vector3 currentRotation = transform.eulerAngles;
        currentRotation.x = Mathf.Clamp(currentRotation.x, -maxTiltAngle, maxTiltAngle);
        currentRotation.z = Mathf.Clamp(currentRotation.z, -maxTiltAngle, maxTiltAngle);
        transform.eulerAngles = currentRotation;
        
        float thrust = maxThrust * (verticalInput + 1f) / 2f;
        rb.AddForce(Vector3.up * thrust, ForceMode.Force);
    }
    
    void ApplyThrustAndMovement()
    {
        float hoverForce = rb.mass * Mathf.Abs(Physics.gravity.y);
        rb.AddForce(Vector3.up * hoverForce, ForceMode.Force);
        rb.linearVelocity *= (1f - dampingForce * Time.fixedDeltaTime);
    }
    
    void FollowTrajectory()
    {
    }
    
    public void OnMove(InputValue value)
    {
        moveInput = value.Get<Vector2>();
    }
    
    public void OnLateral(InputValue value)
    {
        lateralInput = value.Get<Vector2>();
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